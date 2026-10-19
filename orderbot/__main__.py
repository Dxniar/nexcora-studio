"""Запуск: python -m orderbot. Один polling-процесс на токен."""
import asyncio
import logging
from aiogram import Bot,Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage,SimpleEventIsolation
from .config import load_config
from .repository import Repository
from .notifications import NotificationService
from .handlers import create_router


def create_dispatcher() -> Dispatcher:
    dp=Dispatcher(storage=MemoryStorage(),events_isolation=SimpleEventIsolation())
    dp.include_router(create_router())
    return dp


async def run_polling(bot,dp,repo,config):
    stop=asyncio.Event()
    worker=asyncio.create_task(NotificationService(repo,bot,config).run(stop),name='nexcora-notifications')
    polling=asyncio.create_task(dp.start_polling(bot,config=config,repo=repo,close_bot_session=False),name='nexcora-polling')
    try:
        done,_=await asyncio.wait((worker,polling),return_when=asyncio.FIRST_COMPLETED)
        for task in done: await task
        if worker in done and not polling.done():
            raise RuntimeError('Фоновая доставка неожиданно остановилась.')
    finally:
        stop.set()
        if not polling.done():
            try: await asyncio.wait_for(dp.stop_polling(),timeout=5)
            except (RuntimeError,asyncio.TimeoutError): polling.cancel()
        if not worker.done(): worker.cancel()
        await asyncio.gather(worker,polling,return_exceptions=True)
        await dp.fsm.close()


async def main():
    config=load_config()
    repo=Repository(config.db_path)
    await repo.initialize()
    bot=Bot(token=config.bot_token)
    dp=create_dispatcher()
    logging.info('Nexcora 2.0 запускается. Остановить: Ctrl+C')
    if not config.admin_id:
        logging.warning('ADMIN_ID не настроен: заявки сохраняются, уведомления владельцу отключены. Узнать ID: /myid.')
    try:
        await run_polling(bot,dp,repo,config)
    finally:
        await bot.session.close()


if __name__=='__main__':
    logging.basicConfig(level=logging.INFO)
    try: asyncio.run(main())
    except KeyboardInterrupt: pass
