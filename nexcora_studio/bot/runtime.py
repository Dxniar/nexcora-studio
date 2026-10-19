"""One polling process supervises delivery and durable file cleanup."""
import asyncio
from contextlib import asynccontextmanager, suppress
import hashlib
import logging
import re
import signal
from aiogram import Bot, Dispatcher
from sqlalchemy import text
from ..cleanup import CleanupWorker
from ..db import Database
from ..models import Heartbeat, utcnow
from ..outbox import OutboxWorker
from ..settings import Settings
from .handlers import create_router
from .sender import AiogramSender

logger = logging.getLogger(__name__)


class RedactSecrets(logging.Filter):
    def __init__(self, secrets):
        super().__init__()
        self.secrets = tuple(value for value in secrets if value)

    def filter(self, record):
        value = record.getMessage()
        for secret in self.secrets: value = value.replace(secret, '[redacted]')
        value = re.sub(r'\b\d{5,}:[A-Za-z0-9_-]{20,}\b', '[redacted]', value)
        value = re.sub(r'(postgres(?:ql)?(?:\+psycopg)?://)[^\s/@]+(?::[^\s/@]+)?@', r'\1[redacted]@', value)
        record.msg, record.args = value, ()
        # Exception chains may include HTTP URLs, file contents or credentials.
        if record.exc_info: record.exc_info, record.exc_text = None, None
        return True


def configure_logging(settings):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    redaction = RedactSecrets([settings.bot_token, settings.database_url, settings.s3_access_key, settings.s3_secret_key])
    for handler in logging.getLogger().handlers: handler.addFilter(redaction)
    # Upstream update/error logging can contain message text. Keep only our safe logs.
    logging.getLogger('aiogram').disabled = True
    logging.getLogger('aiogram.event').disabled = True
    logging.getLogger('aiogram.dispatcher').disabled = True
    logging.getLogger('aiohttp').setLevel(logging.CRITICAL)


@asynccontextmanager
async def polling_lock(database, bot_token):
    """A session-level lock stays held for the polling process lifetime."""
    if database.engine.dialect.name != 'postgresql':
        yield None  # Disposable local test databases never run real polling.
        return
    key = int.from_bytes(hashlib.sha256(bot_token.encode()).digest()[:8], 'big', signed=True)
    async with database.engine.connect() as connection:
        connection = await connection.execution_options(isolation_level='AUTOCOMMIT')
        acquired = await connection.scalar(text('SELECT pg_try_advisory_lock(:key)'), {'key': key})
        if not acquired: raise RuntimeError('A polling process is already running for this bot.')
        backend_pid = await connection.scalar(text('SELECT pg_backend_pid()'))
        async def verify_lock():
            # A broken/replaced DB connection releases its advisory lock. Stop
            # polling before another process can take over indefinitely.
            if await connection.scalar(text('SELECT pg_backend_pid()')) != backend_pid:
                raise RuntimeError('The polling database lock was lost.')
        try: yield verify_lock
        finally:
            with suppress(Exception):
                await connection.execute(text('SELECT pg_advisory_unlock(:key)'), {'key': key})


async def heartbeat(database, name):
    async with database.session() as session:
        row = await session.get(Heartbeat, name)
        if row: row.updated_at = utcnow()
        else: session.add(Heartbeat(name=name, updated_at=utcnow()))


async def periodic(database, name, operation, stop, interval):
    while not stop.is_set():
        try:
            await operation()
            await heartbeat(database, name)
        except Exception:
            logger.warning('Background operation failed component=%s', name)
        try: await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError: pass


async def liveness(database, stop, interval, verify_lock=None):
    while not stop.is_set():
        if verify_lock is not None: await verify_lock()
        await heartbeat(database, 'bot')
        try: await asyncio.wait_for(stop.wait(), timeout=interval)
        except TimeoutError: pass


@asynccontextmanager
async def shutdown_signals(stop):
    """Containers send SIGTERM; give leased work time to finish safely."""
    loop = asyncio.get_running_loop()
    installed = []
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous = signal.getsignal(signum)
            try:
                loop.add_signal_handler(signum, stop.set)
                installed.append((signum, previous, True))
            except (NotImplementedError, RuntimeError):
                try:
                    signal.signal(signum, lambda *_: loop.call_soon_threadsafe(stop.set))
                    installed.append((signum, previous, False))
                except (ValueError, OSError): pass
        yield
    finally:
        for signum, previous, native in installed:
            if native: loop.remove_signal_handler(signum)
            signal.signal(signum, previous)


async def run_process(settings=None, *, database=None, storage=None, bot=None, dispatcher=None, stop_event=None, interval=1):
    """Own the bot session; leave a caller-supplied database open for its owner."""
    settings = settings or Settings.from_env(load_file=True)
    owns_database = database is None
    database = database or Database(settings.database_url)
    stop = stop_event or asyncio.Event()
    tasks = []
    try:
        if storage is None:
            from ..storage import S3Storage
            storage = S3Storage(settings)
        bot = bot or Bot(settings.bot_token)
        if dispatcher is None:
            dispatcher = Dispatcher()
            dispatcher.include_router(create_router(settings, database))
        worker, cleanup = OutboxWorker(database, settings, AiogramSender(bot)), CleanupWorker(database, storage)
        async with polling_lock(database, settings.bot_token) as verify_lock:
            await heartbeat(database, 'bot')
            tasks = [
                asyncio.create_task(dispatcher.start_polling(bot, handle_signals=False, close_bot_session=False,
                    allowed_updates=dispatcher.resolve_used_update_types()), name='studio_polling'),
                asyncio.create_task(periodic(database, 'outbox', lambda: worker.run_once(limit=1), stop, interval), name='studio_outbox'),
                asyncio.create_task(periodic(database, 'cleanup', lambda: cleanup.run_once(limit=1), stop, max(interval, 5)), name='studio_cleanup'),
                asyncio.create_task(liveness(database, stop, min(interval, 15), verify_lock), name='studio_liveness'),
                asyncio.create_task(stop.wait(), name='studio_stop'),
            ]
            try:
                finished, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in finished:
                    if task.get_name() != 'studio_stop':
                        # Convert failures to a safe message, without upstream payloads.
                        if task.cancelled() or task.exception() is not None:
                            raise RuntimeError('Bot process stopped unexpectedly.') from None
            finally:
                stop.set()
                for task in tasks:
                    if task.get_name() in ('studio_polling', 'studio_stop'): task.cancel()
                # Finish bounded DB/network work before disposal. Cancelling an
                # async DB connection half-open can leave its driver thread alive.
                try: await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=50)
                except TimeoutError:
                    for task in tasks: task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
    finally:
        if bot is not None: await bot.session.close()
        if owns_database: await database.close()
