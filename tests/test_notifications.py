from aiogram import Bot
from aiogram.methods import SendMessage
from aiogram.exceptions import TelegramRetryAfter, TelegramForbiddenError, TelegramNetworkError
from unittest.mock import patch
from orderbot.config import Config
from repo_helpers import RepoCase
from telegram_stub import RecordingSession


class NotificationTests(RepoCase):
    def worker(self, admin_id=999):
        from orderbot.notifications import NotificationService
        return NotificationService(self.repo,self.bot,Config('123456:TEST',admin_id,self.path))

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.session = RecordingSession()
        self.bot = Bot('123456:TEST',session=self.session)

    async def asyncTearDown(self): await self.bot.session.close()

    async def test_retry_after_survives_worker_restart(self):
        await self.submitted()
        self.session.fail_next(SendMessage,lambda m: TelegramRetryAfter(method=m,message='flood',retry_after=73))
        await self.worker().deliver_due_once()
        event = self.query('SELECT * FROM notification_outbox')[0]
        self.assertEqual(event['next_attempt_at'],1073.0)
        self.clock.value = 1072
        self.assertEqual(await self.worker().deliver_due_once(),0)
        self.clock.value = 1073
        await self.worker().deliver_due_once()
        await self.worker().deliver_due_once()
        self.assertEqual(len(self.session.calls_of(SendMessage,chat_id=999)),2)
        event = self.query('SELECT * FROM notification_outbox')[0]
        self.assertEqual(event['state'],'sent')
        self.assertIsNotNone(event['message_id'])

    async def test_temporary_failure_schedule_and_limit(self):
        await self.submitted()
        self.session.fail_next(SendMessage,lambda m: TelegramNetworkError(method=m,message='offline'),times=5)
        for delay in (10,60,300,1800):
            await self.worker().deliver_due_once()
            event = self.query('SELECT * FROM notification_outbox')[0]
            self.assertEqual(event['next_attempt_at'],self.clock.value+delay)
            self.clock.value += delay
        await self.worker().deliver_due_once()
        self.assertEqual(self.query('SELECT * FROM notification_outbox')[0]['state'],'failed')
        self.assertEqual(len(self.query('SELECT * FROM orders')),1)

    async def test_blocked_client_stays_terminal_and_owner_retry_is_scoped(self):
        order = (await self.submitted()).order
        await self.repo.change_status(999,999,order['id'],0,'discussing')
        self.session.fail_next(SendMessage,lambda m: TelegramForbiddenError(method=m,message='blocked'),chat_id=123)
        self.session.fail_next(SendMessage,lambda m: TelegramForbiddenError(method=m,message='blocked'),chat_id=999)
        with self.assertLogs('orderbot.notifications',level='WARNING'):
            await self.worker().deliver_due_once()
        events = self.query('SELECT * FROM notification_outbox ORDER BY id')
        self.assertTrue(all(e['state']=='failed' for e in events))
        revision = await self.repo.get_user_revision(123)
        await self.repo.set_notifications_enabled(123,False,expected_revision=revision)
        await self.repo.set_notifications_enabled(123,True,expected_revision=revision+1)
        self.assertFalse(await self.repo.retry_owner_event(999,999,events[1]['id']))
        self.assertTrue(await self.repo.retry_owner_event(999,999,events[0]['id']))
        self.clock.value += 99999
        await self.worker().deliver_due_once()
        self.assertEqual(len(self.session.calls_of(SendMessage,chat_id=123)),1)
        self.assertEqual(len(self.session.calls_of(SendMessage,chat_id=999)),2)

    async def test_retarget_and_superseded_status_and_recover(self):
        order = (await self.submitted()).order
        await self.repo.change_status(999,999,order['id'],0,'discussing')
        await self.repo.change_status(999,999,order['id'],1,'in_progress')
        self.execute("UPDATE notification_outbox SET state='delivering' WHERE kind='new_order'")
        await self.repo.recover_notifications()
        await self.worker(777).deliver_due_once()
        self.assertEqual(len(self.session.calls_of(SendMessage,chat_id=999)),0)
        self.assertEqual(len(self.session.calls_of(SendMessage,chat_id=777)),1)
        self.assertEqual(len(self.session.calls_of(SendMessage,chat_id=123)),1)
        self.assertEqual(self.query("SELECT state FROM notification_outbox WHERE status_value='discussing'")[0]['state'],'skipped')

    async def test_opt_out_during_failed_in_flight_send_never_revives_event(self):
        order=(await self.submitted()).order
        await self.repo.change_status(999,999,order['id'],0,'discussing')
        await self.worker().deliver_due_once(limit=1)
        original=self.session.make_request
        async def opt_out_then_fail(bot,method,timeout=None):
            if isinstance(method,SendMessage) and method.chat_id==123:
                self.session.requests.append(method)
                revision=await self.repo.get_user_revision(123)
                await self.repo.set_notifications_enabled(123,False,expected_revision=revision)
                raise TelegramNetworkError(method=method,message='lost response')
            return await original(bot,method,timeout)
        with patch.object(self.session,'make_request',opt_out_then_fail):
            await self.worker().deliver_due_once()
        event=self.query("SELECT * FROM notification_outbox WHERE kind='status_changed'")[0]
        self.assertEqual(event['state'],'skipped')
        revision=await self.repo.get_user_revision(123)
        await self.repo.set_notifications_enabled(123,True,expected_revision=revision)
        self.clock.value+=100
        await self.worker().deliver_due_once()
        self.assertEqual(len(self.session.calls_of(SendMessage,chat_id=123)),1)
