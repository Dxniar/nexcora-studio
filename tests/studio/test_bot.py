"""Offline Telegram envelopes; these tests never getMe, poll or send remotely."""
import asyncio
from datetime import datetime, timezone
from io import StringIO
import logging
import os
import unittest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter
from aiogram.methods import SendMessage
from aiogram.types import Message, Update
from sqlalchemy import select, text
from tests.studio.cases import StudioCase
from tests.studio.helpers import BOT_TOKEN
from tests.studio.pg_sandbox import PgSandbox
from nexcora_studio.runtime import loop_factory


class TelegramSink(BaseSession):
    def __init__(self, failure=None):
        super().__init__()
        self.methods, self.failure, self.closed = [], failure, False

    async def make_request(self, bot, method, timeout=None):
        if not isinstance(method, SendMessage): raise AssertionError('Unexpected Telegram API operation')
        self.methods.append(method)
        if self.failure: raise self.failure
        return Message(message_id=771, date=datetime.now(timezone.utc), chat={'id': method.chat_id, 'type': 'private'}, text=method.text)

    async def stream_content(self, url, **kwargs):
        raise AssertionError('No media downloads permitted')
        yield b''

    async def close(self): self.closed = True


class BotTests(StudioCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.sink = TelegramSink()
        self.bot = Bot(BOT_TOKEN, session=self.sink)
        self.dispatcher = Dispatcher()

    async def asyncTearDown(self):
        await self.bot.session.close()
        await super().asyncTearDown()

    async def command(self, text, user_id=101, chat_type='private'):
        from nexcora_studio.bot.handlers import create_router
        dispatcher = Dispatcher()
        dispatcher.include_router(create_router(self.settings))
        update = Update(update_id=123, message={
            'message_id': 1, 'date': int(datetime.now(timezone.utc).timestamp()),
            'chat': {'id': user_id, 'type': chat_type},
            'from': {'id': user_id, 'is_bot': False, 'first_name': 'Алия'},
            'text': text,
            'entities': [{'type': 'bot_command', 'offset': 0, 'length': len(text.split()[0])}],
        })
        await dispatcher.feed_update(self.bot, update)
        return self.sink.methods[-1]

    async def test_commands_open_role_appropriate_app_pages(self):
        cases = [('/start', 101, '/'), ('/menu', 101, '/'), ('/new', 101, '/draft'),
                 ('/myorders', 101, '/projects'), ('/orders', 101, '/projects'),
                 ('/help', 101, '/'), ('/myid', 101, '/'), ('/owner', 101, '/'),
                 ('/start', 999, '/owner'), ('/orders', 999, '/owner/projects'), ('/new', 999, '/owner')]
        for command, user, path in cases:
            with self.subTest(command=command, user=user):
                answer = await self.command(command, user)
                self.assertEqual(answer.reply_markup.inline_keyboard[0][0].web_app.url, 'http://127.0.0.1:8000' + path)
        self.assertIn('101', (await self.command('/myid')).text)

    async def test_start_payload_never_grants_owner_role_and_group_has_no_webapp_button(self):
        answer = await self.command('/start owner', 101)
        self.assertEqual(answer.reply_markup.inline_keyboard[0][0].web_app.url, 'http://127.0.0.1:8000/')
        group = await self.command('/orders', 101, 'group')
        self.assertIsNone(group.reply_markup)
        self.assertIn('личн', group.text.lower())

    async def test_sender_uses_bounded_telegram_call_and_project_deep_link(self):
        from nexcora_studio.bot.sender import AiogramSender
        from nexcora_studio.outbox import Notification
        message_id = await AiogramSender(self.bot).send(Notification(9, 2, 101, 'proposal_sent', 'https://studio.test/projects/2'))
        self.assertEqual(message_id, 771)
        sent = self.sink.methods[-1]
        self.assertEqual(sent.chat_id, 101)
        self.assertIn('#2', sent.text)
        self.assertEqual(sent.reply_markup.inline_keyboard[0][0].web_app.url, 'https://studio.test/projects/2')

    async def test_sender_maps_errors_to_safe_failure_without_payload(self):
        from nexcora_studio.bot.sender import AiogramSender
        from nexcora_studio.outbox import DeliveryFailure, Notification
        method = SendMessage(chat_id=101, text='unused')
        cases = [(TelegramForbiddenError(method, 'private payload'), 'forbidden', True),
                 (TelegramNetworkError(method, 'private payload'), 'temporary', False),
                 (TelegramRetryAfter(method, 'private payload', retry_after=45), 'retry_after', False)]
        for failure, code, permanent in cases:
            self.sink.failure = failure
            with self.assertRaises(DeliveryFailure) as caught:
                await AiogramSender(self.bot).send(Notification(9, 2, 101, 'proposal_sent', 'https://studio.test/projects/2'))
            self.assertEqual((caught.exception.code, caught.exception.permanent), (code, permanent))
            self.assertNotIn('private payload', str(caught.exception))

    async def test_runtime_stops_workers_closes_session_and_records_heartbeat(self):
        from nexcora_studio.bot.runtime import run_process
        from nexcora_studio.models import Heartbeat
        stop = asyncio.Event()
        started = asyncio.Event()
        class SyntheticPolling:
            def resolve_used_update_types(self): return ['message']
            async def start_polling(inner, *args, **kwargs):
                started.set()
                await asyncio.Event().wait()
        class Storage:
            async def delete(inner, key): raise AssertionError('No test cleanup object should exist')
        task = asyncio.create_task(run_process(self.settings, database=self.db, storage=Storage(), bot=self.bot, dispatcher=SyntheticPolling(), stop_event=stop, interval=0.01))
        await asyncio.wait_for(started.wait(), timeout=3)
        for _ in range(100):
            async with self.db.session() as session:
                heartbeat = await session.get(Heartbeat, 'outbox')
            if heartbeat: break
            await asyncio.sleep(0.01)
        self.assertIsNotNone(heartbeat)
        stop.set()
        await asyncio.wait_for(task, timeout=3)
        self.assertTrue(self.sink.closed)

    async def test_runtime_cancellation_also_closes_bot_session(self):
        from nexcora_studio.bot.runtime import run_process
        entered = asyncio.Event()
        class SyntheticPolling:
            def resolve_used_update_types(inner): return ['message']
            async def start_polling(inner, *args, **kwargs):
                entered.set()
                await asyncio.Event().wait()
        class Storage:
            async def delete(inner, key): pass
        task = asyncio.create_task(run_process(self.settings, database=self.db, storage=Storage(), bot=self.bot, dispatcher=SyntheticPolling(), interval=0.01))
        await asyncio.wait_for(entered.wait(), 3)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        self.assertTrue(self.sink.closed)

    async def test_liveness_heartbeat_keeps_updating_while_polling_is_alive(self):
        from nexcora_studio.bot.runtime import run_process
        from nexcora_studio.auth import as_utc
        from nexcora_studio.models import Heartbeat
        stop, entered = asyncio.Event(), asyncio.Event()
        class SyntheticPolling:
            def resolve_used_update_types(inner): return ['message']
            async def start_polling(inner, *args, **kwargs):
                entered.set()
                await asyncio.Event().wait()
        class Storage:
            async def delete(inner, key): pass
        task = asyncio.create_task(run_process(self.settings, database=self.db, storage=Storage(), bot=self.bot, dispatcher=SyntheticPolling(), stop_event=stop, interval=0.01))
        await asyncio.wait_for(entered.wait(), timeout=3)
        async with self.db.session() as session: initial = as_utc((await session.get(Heartbeat, 'bot')).updated_at)
        await asyncio.sleep(0.12)
        async with self.db.session() as session: latest = as_utc((await session.get(Heartbeat, 'bot')).updated_at)
        stop.set()
        await asyncio.wait_for(task, timeout=3)
        self.assertGreater(latest, initial)

    async def test_log_filter_removes_tokens_and_credentials(self):
        from nexcora_studio.bot.runtime import RedactSecrets
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        handler.addFilter(RedactSecrets([BOT_TOKEN]))
        logger = logging.getLogger('studio_synthetic_redaction')
        logger.addHandler(handler)
        logger.setLevel(logging.WARNING)
        try: logger.warning('Failed https://api.telegram.org/bot%s/sendMessage database=postgresql://user:pw@db/app', BOT_TOKEN)
        finally: logger.removeHandler(handler)
        self.assertNotIn(BOT_TOKEN, stream.getvalue())
        self.assertNotIn('user:pw', stream.getvalue())


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Dedicated PostgreSQL TEST_DATABASE_URL required')
class PostgresBotTests(BotTests):
    async def test_polling_lock_does_not_hold_a_long_database_transaction(self):
        import hashlib
        from sqlalchemy import text
        from nexcora_studio.bot.runtime import polling_lock
        key = int.from_bytes(hashlib.sha256(BOT_TOKEN.encode()).digest()[:8], 'big')
        async with polling_lock(self.db, BOT_TOKEN):
            async with self.db.session() as session:
                state = await session.scalar(text("SELECT state FROM pg_stat_activity WHERE pid = (SELECT pid FROM pg_locks WHERE locktype='advisory' AND classid=:high AND objid=:low AND objsubid=1)"), {'high': key >> 32, 'low': key & 0xffffffff})
                self.assertEqual(state, 'idle')

    loop_factory = staticmethod(loop_factory)

    async def target_url(self):
        self.pg = PgSandbox()
        return await self.pg.start()

    async def test_polling_lock_excludes_second_process_until_release(self):
        from nexcora_studio.bot.runtime import polling_lock
        async with polling_lock(self.db, BOT_TOKEN):
            with self.assertRaises(RuntimeError):
                async with polling_lock(self.db, BOT_TOKEN): self.fail('Duplicate poller acquired lock')
        async with polling_lock(self.db, BOT_TOKEN): pass

    async def test_runtime_stops_if_its_polling_lock_connection_is_lost(self):
        import hashlib
        from nexcora_studio.bot.runtime import run_process
        entered = asyncio.Event()
        class SyntheticPolling:
            def resolve_used_update_types(inner): return ['message']
            async def start_polling(inner, *args, **kwargs):
                entered.set()
                await asyncio.Event().wait()
        class Storage:
            async def delete(inner, key): pass
        task = asyncio.create_task(run_process(self.settings, database=self.db, storage=Storage(), bot=self.bot, dispatcher=SyntheticPolling(), interval=0.01))
        await asyncio.wait_for(entered.wait(), 3)
        # Terminate only this test's advisory-lock connection, never the cluster.
        key = int.from_bytes(hashlib.sha256(BOT_TOKEN.encode()).digest()[:8], 'big')
        async with self.db.session() as session:
            pid = await session.scalar(text("SELECT pid FROM pg_locks WHERE locktype='advisory' AND classid=:high AND objid=:low AND objsubid=1"), {'high': key >> 32, 'low': key & 0xffffffff})
            self.assertIsNotNone(pid)
            await session.execute(text('SELECT pg_terminate_backend(:pid)'), {'pid': pid})
        try:
            with self.assertRaises(RuntimeError): await asyncio.wait_for(task, timeout=2)
        finally:
            if not task.done(): task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        self.assertTrue(self.sink.closed)
