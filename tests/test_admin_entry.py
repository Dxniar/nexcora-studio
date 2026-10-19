from orderbot.callbacks import Action, encode_action
from orderbot.config import Config
from ui_helpers import UiCase


class AdminEntryTests(UiCase):
    async def test_owner_start_and_menu_open_cabinet_with_current_counts(self):
        await self.submitted()
        await self.repo.change_status(999,999,1,0,'in_progress')
        for command in ('/start','/menu'):
            with self.subTest(command=command):
                await self.say(command,user_id=999)
                screen=self.session.last_message(999)
                self.assertIn('Кабинет владельца',screen.text)
                self.assertIn('Всего: 1',screen.text)
                self.assertIn('В работе: 1',screen.text)
                self.assertNotIn('Обсудить проект',self.labels(screen))
                self.button_data(screen,'Клиентское меню')
        await self.press('В работе',user_id=999)
        await self.press('№1',user_id=999)
        self.assertIn('Айша',self.session.last_message(999).text)

    async def test_owner_client_menu_round_trip_preserves_draft(self):
        saved=await self.completed_draft(999)
        await self.say('/start',user_id=999)
        await self.press('Клиентское меню',user_id=999)
        screen=self.session.last_message(999)
        self.button_data(screen,'Обсудить проект')
        await self.press('Продолжить заявку',user_id=999)
        self.assertIn('Проверьте заявку',self.session.last_message(999).text)
        await self.press('Главное меню',user_id=999)
        self.button_data(self.session.last_message(999),'Обсудить проект')
        await self.press('Кабинет владельца',user_id=999)
        self.assertIn('Кабинет владельца',self.session.last_message(999).text)
        self.assertEqual(await self.repo.get_draft(999),saved)
        self.assertEqual(self.query('SELECT * FROM orders'),[])

    async def test_clients_and_unconfigured_owner_get_only_client_menu(self):
        for admin_id in (999,None):
            self.config=Config('123456:TEST',admin_id,self.path)
            for command in ('/start','/menu'):
                await self.say(command)
                screen=self.session.last_message(123)
                self.button_data(screen,'Обсудить проект')
                self.assertNotIn('Кабинет владельца',self.labels(screen))
                self.assertNotIn('Всего:',screen.text)
        await self.say('/start',user_id=999,chat_id=-100,chat_type='group')
        self.assertFalse(any(chat==-100 for chat,_ in self.session.messages))

    async def test_owner_rotation_changes_entry_and_denies_old_dashboard(self):
        await self.say('/start',user_id=999)
        old_action=self.button_data(self.session.last_message(999),'Новые')
        self.config=Config('123456:TEST',777,self.path)
        await self.say('/start',user_id=999)
        self.button_data(self.session.last_message(999),'Обсудить проект')
        await self.click(old_action,user_id=999)
        self.assertIn('администратору',self.session.last_message(999).text)
        await self.say('/start',user_id=777)
        self.assertIn('Кабинет владельца',self.session.last_message(777).text)

    async def test_forged_admin_actions_in_own_private_chat_are_denied(self):
        await self.submitted()
        self.execute("UPDATE notification_outbox SET state='failed'")
        orders_before=self.query('SELECT * FROM orders')
        events_before=self.query('SELECT * FROM notification_outbox')
        await self.say('/start',user_id=456)
        for action in (Action('admin','0',0,'list','all'),
                       Action('admin','0',0,'failures'),
                       Action('admin','1',0,'view'),
                       Action('admin','1',0,'set','in_progress'),
                       Action('retry','1',0,'set')):
            await self.click(encode_action(action),user_id=456)
            screen=self.session.last_message(456)
            self.assertIn('администратору',screen.text)
            self.assertNotIn('Айша',screen.text)
            self.assertNotIn('Всего:',screen.text)
            self.assertNotIn('Контакт клиента',self.labels(screen))
        self.assertEqual(self.query('SELECT * FROM orders'),orders_before)
        self.assertEqual(self.query('SELECT * FROM notification_outbox'),events_before)

    def labels(self,screen):
        return '\n'.join(button.text for row in screen.reply_markup.inline_keyboard for button in row)
