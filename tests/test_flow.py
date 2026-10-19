"""Регрессии v1, обновлённые под постоянную анкету и inline-кнопки v2."""
import asyncio
import html
from unittest.mock import patch
from aiogram.methods import SendMessage
from aiogram.exceptions import TelegramForbiddenError
from orderbot.config import Config
from ui_helpers import UiCase


class FlowTests(UiCase):
    async def test_confirmation_and_contact(self):
        await self.draft()
        self.assertEqual(self.query('SELECT * FROM orders'),[])
        await self.press('Отправить заявку')
        row=self.query('SELECT * FROM orders')[0]
        self.assertEqual(row['phone'],'')
        self.assertEqual(row['username'],'client_user')
        await self.deliver()
        card=self.session.last_message(999)
        self.assertIn('https://t.me/client_user',[b.url for r in card.reply_markup.inline_keyboard for b in r])

    async def test_missing_username(self):
        await self.draft(username=None)
        self.assertIn('username',self.session.last_message(123).text)
        self.assertIn('@DXNIAR',self.session.last_message(123).text)
        await self.press('Отправить заявку',username=None)
        self.assertIsNone(self.query('SELECT * FROM orders')[0]['username'])
        await self.deliver()
        self.assertIn('tg://user?id=123',[b.url for r in self.session.last_message(999).reply_markup.inline_keyboard for b in r])

    async def test_simultaneous_confirmation(self):
        review=await self.draft()
        data=self.button_data(review,'Отправить заявку')
        await asyncio.gather(self.click(data,source=review),self.click(data,source=review))
        self.assertEqual(len(self.query('SELECT * FROM orders')),1)
        self.assertEqual(len(self.query('SELECT * FROM notification_outbox')),1)

    async def test_cancel_and_start(self):
        await self.draft()
        before=await self.repo.get_draft(123)
        await self.say('/start')
        self.assertEqual(await self.repo.get_draft(123),before)
        for command in ('/cancel','Отмена'):
            await self.say(command)
            self.assertIsNone(await self.repo.get_draft(123))
            self.assertEqual(self.query('SELECT * FROM orders'),[])
            if command=='/cancel': await self.draft()

    async def test_invalid_input_stays_on_step(self):
        await self.say('/new')
        for value in (None,'Неизвестная услуга'):
            await self.say(value)
            self.assertEqual((await self.repo.get_draft(123)).step,'service')
        await self.press('Telegram-бот')
        for value in (None,' ', 'x'*9,'x'*2001):
            await self.say(value)
            self.assertEqual((await self.repo.get_draft(123)).step,'description')
        await self.say('x'*2000)
        await self.press('Пока не знаю')
        await self.press('Пропустить')
        for value in (None,'A','a'*81):
            await self.say(value)
            self.assertEqual((await self.repo.get_draft(123)).step,'name')
        await self.say('A'*80)
        await self.press('Отправить заявку')
        self.assertEqual(len(self.query('SELECT * FROM orders')[0]['comment']),2000)

    async def test_database_error_keeps_draft(self):
        review=await self.draft()
        data=self.button_data(review,'Отправить заявку')
        with patch.object(self.repo,'submit_draft',side_effect=OSError('offline')):
            with self.assertLogs('orderbot.handlers',level='ERROR'):
                await self.click(data,source=review)
        self.assertIsNotNone(await self.repo.get_draft(123))
        self.assertEqual(self.query('SELECT * FROM orders'),[])
        await self.click(data,source=review)
        self.assertEqual(len(self.query('SELECT * FROM orders')),1)

    async def test_notification_error_preserves_order(self):
        await self.draft()
        await self.press('Отправить заявку')
        self.session.fail_next(SendMessage,lambda m: TelegramForbiddenError(method=m,message='blocked'),chat_id=999)
        with self.assertLogs('orderbot.notifications',level='WARNING'): await self.deliver()
        self.assertEqual(len(self.query('SELECT * FROM orders')),1)
        self.assertIn('№1',self.client_text())
        self.assertNotIn('Уведомление отправлено',self.client_text())

    async def test_admin_not_configured(self):
        self.config=Config('123456:TEST',None,self.path)
        await self.draft()
        await self.press('Отправить заявку')
        self.assertEqual(len(self.query('SELECT * FROM orders')),1)
        self.assertEqual(self.query('SELECT * FROM notification_outbox'),[])
        self.assertIn('DXNIAR',self.client_text())

    async def test_private_orders_and_delete_own_data(self):
        await self.draft()
        await self.press('Отправить заявку')
        await self.say('/orders')
        self.assertIn('администратору',self.session.last_message(123).text)
        await self.say('/delete_my_data',user_id=456)
        await self.press('Удалить мои данные',user_id=456)
        self.assertEqual(len(self.query('SELECT * FROM orders')),1)
        await self.say('/orders',user_id=999)
        await self.press('№1',user_id=999)
        self.assertIn('Айша',self.session.last_message(999).text)
        await self.say('/delete_my_data')
        await self.press('Удалить мои данные')
        self.assertEqual(self.query('SELECT * FROM orders'),[])

    async def test_menu_links(self):
        await self.say('/start')
        await self.press('Услуги')
        await self.press('API-интеграция')
        self.assertIn('обмен',self.session.last_message(123).text)
        await self.press('Главное меню')
        await self.press('Связаться')
        self.assertIn('https://t.me/DXNIAR',[b.url for r in self.session.last_message(123).reply_markup.inline_keyboard for b in r])
        await self.say('/myid')
        self.assertIn('123',self.session.last_message(123).text)

    async def test_escaped_maximum_input(self):
        await self.draft(description='<'*2000,name='<'*80)
        await self.press('Отправить заявку')
        await self.deliver()
        sends=self.session.calls_of(SendMessage,chat_id=999)
        self.assertIn('&lt;',sends[0].text)
        for item in sends: self.assertLessEqual(len(html.unescape(item.text).encode('utf-16-le'))//2,3500)
