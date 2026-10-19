from unittest.mock import patch
from aiogram.methods import AnswerCallbackQuery
from aiogram.methods import SendMessage
from aiogram.exceptions import TelegramNetworkError
from ui_helpers import UiCase


class ClientFlowTests(UiCase):
    async def test_legacy_submit_text_must_show_revision_bound_review(self):
        await self.draft()
        await self.press('Изменить задачу')
        self.session.fail_next(SendMessage,lambda m: TelegramNetworkError(method=m,message='offline'),chat_id=123)
        with self.assertLogs('orderbot.handlers',level='WARNING'):
            await self.say('Новая ещё не просмотренная задача')
        await self.say('Отправить')
        self.assertEqual(self.query('SELECT * FROM orders'),[])
        self.assertIn('Новая ещё не просмотренная задача',self.session.last_message(123).text)
        await self.press('Отправить заявку')
        self.assertEqual(len(self.query('SELECT * FROM orders')),1)

    async def test_submission_replay_shows_actual_status(self):
        review=await self.draft()
        data=self.button_data(review,'Отправить заявку')
        await self.click(data,source=review)
        await self.repo.change_status(999,999,1,0,'in_progress')
        await self.click(data)
        self.assertIn('В работе',self.session.last_message(123).text)

    async def test_my_orders_list_includes_submission_date(self):
        await self.submitted()
        await self.say('/myorders')
        labels=[b.text for row in self.session.last_message(123).reply_markup.inline_keyboard for b in row]
        self.assertTrue(any('№1' in label and '1970-01-01' in label for label in labels))

    async def test_edit_submit_view_and_restart_replay(self):
        review=await self.draft()
        old=self.button_data(review,'Отправить заявку')
        await self.press('Изменить задачу')
        await self.say('Исправленное описание задачи')
        await self.click(old,source=review)
        self.assertEqual(self.query('SELECT * FROM orders'),[])
        submitted=self.button_data(self.session.last_message(123),'Отправить заявку')
        await self.press('Отправить заявку')
        row=self.query('SELECT * FROM orders')[0]
        self.assertEqual(row['comment'],'Исправленное описание задачи')
        self.assertEqual(row['client_name'],'Айша')
        self.assertEqual(row['budget'],'')
        current_data=self.button_data(self.session.last_message(123),'Открыть заявку')
        await self.click(current_data)
        self.assertIn('Получена',self.session.last_message(123).text)
        # The successful confirmation payload remains valid after restarting services.
        await self.restart_dispatcher()
        for _ in range(2): await self.click(submitted)
        self.assertEqual(len(self.query('SELECT * FROM orders')),1)
        self.assertEqual(len(self.query('SELECT * FROM notification_outbox')),1)
        self.assertIn('№1',self.session.last_message(123).text)

    async def test_start_menu_and_new_do_not_destroy_draft(self):
        await self.say('/new')
        await self.press('Telegram-бот')
        await self.say('Описание черновика клиента')
        saved=await self.repo.get_draft(123)
        await self.say('/start')
        self.assertEqual(await self.repo.get_draft(123),saved)
        await self.restart_dispatcher()
        await self.press('Продолжить заявку')
        self.assertIn('бюджету',self.session.last_message(123).text)
        await self.say('/new')
        self.assertEqual(await self.repo.get_draft(123),saved)
        await self.press('Начать заново')
        self.assertNotEqual((await self.repo.get_draft(123)).id,saved.id)

    async def test_foreign_and_group_callbacks_and_bad_input(self):
        review=await self.draft(description='Секретное описание клиента 123')
        payload=self.button_data(review,'Отправить заявку')
        await self.click(payload,user_id=456,source=review)
        self.assertEqual(self.query('SELECT * FROM orders'),[])
        self.assertNotIn('Секретное описание клиента 123',self.client_text(456))
        await self.click(payload,source=review,chat_id=-100,chat_type='group')
        self.assertEqual(self.query('SELECT * FROM orders'),[])
        await self.click('broken',source=review)
        self.assertEqual(self.query('SELECT * FROM orders'),[])
        draft=await self.repo.get_draft(123)
        await self.say('/unknown')
        self.assertEqual(await self.repo.get_draft(123),draft)
        ids=[m.callback_query_id for m in self.session.calls_of(AnswerCallbackQuery)]
        self.assertEqual(len(ids),len(set(ids)))

    async def test_delete_confirmation_and_database_error(self):
        await self.draft()
        await self.press('Отправить заявку')
        await self.say('/delete_my_data')
        self.assertEqual(len(self.query('SELECT * FROM orders')),1)
        await self.press('Удалить мои данные')
        self.assertEqual(self.query('SELECT * FROM orders'),[])
        await self.say('/myorders')
        self.assertIn('пока нет',self.session.last_message(123).text)
        with patch.object(self.repo,'list_user_orders',side_effect=OSError('offline')):
            with self.assertLogs('orderbot.handlers',level='ERROR'):
                await self.say('/myorders')
        self.assertIn('попробуйте',self.session.last_message(123).text.lower())
