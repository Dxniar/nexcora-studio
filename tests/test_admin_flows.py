from aiogram.methods import SendMessage
from aiogram.exceptions import TelegramForbiddenError
from orderbot.config import Config
from orderbot.models import STATUSES
from ui_helpers import UiCase


class AdminFlowTests(UiCase):
    async def test_extreme_page_is_safe_for_orders_and_failures(self):
        from orderbot.callbacks import Action,encode_action
        await self.submitted()
        await self.say('/orders',user_id=999)
        for verb,arg in (('list','all'),('failures','')):
            payload=encode_action(Action('admin',str(2**63-1),0,verb,arg))
            await self.click(payload,user_id=999)
            self.assertIsNotNone(self.session.last_message(999).reply_markup)
        self.assertEqual(len(self.query('SELECT * FROM orders')),1)

    async def test_owner_filters_and_changes_status_with_stale_buttons(self):
        for _ in range(7):
            await self.submitted()
            self.clock.value+=31
        await self.say('/orders',user_id=999)
        self.assertIn('Всего: 7',self.session.last_message(999).text)
        await self.press('Далее',user_id=999)
        buttons=[b for r in self.session.last_message(999).reply_markup.inline_keyboard for b in r]
        self.assertEqual(len([b for b in buttons if b.text.startswith('№')]),2)
        await self.press('№2',user_id=999)
        source=self.session.last_message(999)
        stale=self.button_data(source,'Закрыта')
        await self.press('В работе',user_id=999)
        await self.click(stale,user_id=999,source=source)
        self.assertIn('В работе',self.session.last_message(999).text)
        self.assertEqual((await self.repo.get_admin_order(999,999,2))['status'],'in_progress')
        self.assertEqual(len(self.query("SELECT * FROM notification_outbox WHERE kind='status_changed'")),1)

    async def test_non_owner_and_former_owner_and_group_cannot_change(self):
        await self.submitted()
        await self.say('/orders',user_id=999)
        await self.press('№1',user_id=999)
        source=self.session.last_message(999)
        data=self.button_data(source,'В работе')
        await self.click(data,user_id=456,source=source)
        await self.click(data,user_id=999,source=source,chat_id=-100,chat_type='group')
        self.config=Config('123456:TEST',777,self.path)
        await self.click(data,user_id=999,source=source)
        self.assertEqual((await self.repo.get_user_order(123,1))['status'],'new')
        self.assertNotIn('Айша',self.client_text(456))

    async def test_failures_panel_retries_only_owner_event(self):
        await self.submitted()
        self.session.fail_next(SendMessage,lambda m: TelegramForbiddenError(method=m,message='blocked'),chat_id=999)
        with self.assertLogs('orderbot.notifications',level='WARNING'): await self.deliver()
        await self.say('/orders',user_id=999)
        await self.press('Недоставленные',user_id=999)
        await self.press('Повторить владельцу',user_id=999)
        await self.deliver()
        self.assertEqual(self.query('SELECT state FROM notification_outbox')[0]['state'],'sent')
        self.assertEqual(len(self.query('SELECT * FROM notification_outbox')),1)
