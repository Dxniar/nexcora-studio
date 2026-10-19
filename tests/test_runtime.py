import asyncio
from unittest.mock import patch,AsyncMock
from aiogram import Bot
from orderbot import __main__ as app
from orderbot.config import Config
from repo_helpers import RepoCase
from telegram_stub import RecordingSession


class RuntimeTests(RepoCase):
    async def scenario(self,mode):
        started=asyncio.Event()
        worker_finished=asyncio.Event()
        polling_finished=asyncio.Event()
        class Worker:
            def __init__(self,*args): pass
            async def run(self,stop):
                started.set()
                try:
                    if mode=='worker_error':
                        await asyncio.sleep(0)
                        raise RuntimeError('worker failed')
                    await stop.wait()
                finally: worker_finished.set()
        async def polling(*args,**kwargs):
            await started.wait()
            try:
                if mode=='polling_error': raise RuntimeError('polling failed')
                if mode in ('worker_error','cancel'): await asyncio.Event().wait()
            finally: polling_finished.set()
        session=RecordingSession()
        session.close=AsyncMock()
        bot=Bot('123456:TEST',session=session)
        dp=app.create_dispatcher()
        dp.start_polling=AsyncMock(side_effect=polling)
        with patch.object(app,'load_config',return_value=Config('123456:TEST',999,self.path)), \
             patch.object(app,'Repository',return_value=self.repo),patch.object(app,'Bot',return_value=bot), \
             patch.object(app,'create_dispatcher',return_value=dp),patch.object(app,'NotificationService',Worker):
            if mode.endswith('error'):
                with self.assertRaises(RuntimeError): await app.main()
            elif mode=='cancel':
                task=asyncio.create_task(app.main())
                await asyncio.wait_for(started.wait(),timeout=2)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError): await task
            else: await app.main()
        self.assertTrue(worker_finished.is_set())
        self.assertTrue(polling_finished.is_set())
        session.close.assert_awaited_once()
        self.assertIs(dp.start_polling.call_args.kwargs['repo'],self.repo)
        self.assertFalse(any(task.get_name().startswith('nexcora-') and not task.done()
                             for task in asyncio.all_tasks()))

    async def test_polling_error_stops_worker_and_closes_session(self): await self.scenario('polling_error')
    async def test_worker_error_stops_polling_and_closes_session(self): await self.scenario('worker_error')
    async def test_normal_return_stops_worker_and_closes_session(self): await self.scenario('normal')
    async def test_cancellation_stops_worker_and_closes_session(self): await self.scenario('cancel')
