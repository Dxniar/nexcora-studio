"""Real update routing and durable locale selection; Telegram is an offline sink."""
from datetime import datetime, timezone
import unittest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, SendMessage
from aiogram.types import Message, Update
from sqlalchemy import func, select
from nexcora_studio.models import Session, User
from tests.studio.cases import StudioCase
from tests.studio.helpers import BOT_TOKEN


class LanguageSink(BaseSession):
    def __init__(self):
        super().__init__()
        self.messages, self.callbacks = [], []

    async def make_request(self, bot, method, timeout=None):
        if isinstance(method, SendMessage):
            self.messages.append(method)
            return Message(message_id=771, date=datetime.now(timezone.utc),
                           chat={'id': method.chat_id, 'type': 'private'}, text=method.text)
        if isinstance(method, AnswerCallbackQuery):
            self.callbacks.append(method)
            return True
        raise AssertionError('Unexpected Telegram API operation')

    async def stream_content(self, url, **kwargs):
        raise AssertionError('No media downloads permitted')
        yield b''

    async def close(self): pass


class BotLanguageTests(StudioCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.sink = LanguageSink()
        self.bot = Bot(BOT_TOKEN, session=self.sink)

    async def asyncTearDown(self):
        await self.bot.session.close()
        await super().asyncTearDown()

    async def feed(self, *, command=None, callback=None, actor=101, locale='ru', chat_type='private', database=True):
        from nexcora_studio.bot.handlers import create_router
        dispatcher = Dispatcher()
        dispatcher.include_router(create_router(self.settings, self.db) if database else create_router(self.settings))
        user = {'id': actor, 'is_bot': False, 'first_name': 'Алия', 'language_code': locale}
        message = {'message_id': 1, 'date': int(datetime.now(timezone.utc).timestamp()),
                   'chat': {'id': actor if chat_type == 'private' else -1001, 'type': chat_type}, 'from': user}
        if command:
            message.update(text=command, entities=[{'type': 'bot_command', 'offset': 0, 'length': len(command.split()[0])}])
            update = Update(update_id=123, message=message)
        else:
            message['from'] = {'id': 123456, 'is_bot': True, 'first_name': 'Studio'}
            update = Update(update_id=124, callback_query={'id': 'language-test', 'from': user,
                            'chat_instance': 'synthetic-chat', 'data': callback, 'message': message})
        await dispatcher.feed_update(self.bot, update)
        return self.sink.messages[-1] if self.sink.messages else None

    async def language(self, user_id=101):
        async with self.db.session() as session:
            return (await session.get(User, user_id)).language_code

    async def test_no_database_command_uses_telegram_language(self):
        answer = await self.feed(command='/help', locale='en', database=False)
        self.assertIn('Open the app', answer.text)
        self.assertEqual(answer.reply_markup.inline_keyboard[0][0].text, 'Open Nexcora Studio')

    async def test_new_bot_user_detects_locale_without_creating_web_session(self):
        answer = await self.feed(command='/start', actor=303, locale='kk-KZ')
        self.assertIn('тапсырманы', answer.text)
        self.assertEqual(await self.language(303), 'kk')
        async with self.db.session() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(Session)), 0)

    async def test_saved_locale_survives_telegram_language_and_new_router(self):
        async with self.db.session() as session:
            (await session.get(User, 101)).language_code = 'en'
        answer = await self.feed(command='/help', locale='ru')
        self.assertIn('Open the app', answer.text)
        answer = await self.feed(command='/start', locale='kk')
        self.assertEqual(answer.reply_markup.inline_keyboard[1][0].text, 'Language')
        self.assertEqual(await self.language(), 'en')

    async def test_language_menu_and_selection_persist_for_actual_callback_actor(self):
        answer = await self.feed(command='/language')
        choices = answer.reply_markup.inline_keyboard
        self.assertEqual([button.callback_data for row in choices for button in row],
                         ['language:ru', 'language:en', 'language:kk'])
        await self.feed(callback='language:kk')
        self.assertEqual(await self.language(), 'kk')
        self.assertEqual(await self.language(202), 'ru')
        answer = await self.feed(command='/help', locale='ru')
        self.assertIn('қосымшаны', answer.text)
        self.assertEqual(answer.reply_markup.inline_keyboard[0][0].text, 'Nexcora Studio ашу')

    async def test_unknown_or_forged_selection_never_changes_language(self):
        for value in ('language:de', 'language:en:202', 'language:EN', 'language:'):
            await self.feed(callback=value)
            self.assertEqual(await self.language(), 'ru')
            self.assertEqual(await self.language(202), 'ru')
        self.assertTrue(self.sink.callbacks)

    async def test_group_callback_cannot_create_or_change_user_preference(self):
        await self.feed(callback='language:en', actor=303, chat_type='group')
        async with self.db.session() as session:
            self.assertIsNone(await session.get(User, 303))


class NotificationLanguageTests(StudioCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        from nexcora_studio.services.projects import ProjectService
        self.now = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
        portal = ProjectService(self.db, self.settings, clock=lambda: self.now)
        draft = await portal.get_draft(self.client)
        draft = await portal.save_draft(self.client, {'service_id': 'bot', 'name': 'Алия',
            'description': 'Бот для записи клиентов'}, draft['version'])
        await portal.submit(self.client, draft['id'], draft['version'], 0, 'submit')

    async def test_delivery_uses_recipient_locale_changed_after_event_was_queued(self):
        from nexcora_studio.outbox import OutboxWorker
        from tests.studio.test_outbox import SyntheticSender
        async with self.db.session() as session:
            (await session.get(User, 101)).language_code = 'kk'
            (await session.get(User, 999)).language_code = 'en'
        sender = SyntheticSender()
        worker = OutboxWorker(self.db, self.settings, sender, clock=lambda: self.now)
        await worker.run_once()
        self.assertEqual(sender.deliveries[0].language_code, 'en')

    async def test_client_delivery_uses_its_own_saved_locale(self):
        from nexcora_studio.models import Outbox
        from nexcora_studio.outbox import OutboxWorker
        from tests.studio.test_outbox import SyntheticSender
        async with self.db.session() as session:
            row = await session.scalar(select(Outbox))
            row.recipient_role, row.recipient_id = 'client', 101
            (await session.get(User, 101)).language_code = 'kk'
            (await session.get(User, 999)).language_code = 'en'
        sender = SyntheticSender()
        await OutboxWorker(self.db, self.settings, sender, clock=lambda: self.now).run_once()
        self.assertEqual(sender.deliveries[0].language_code, 'kk')

    async def test_client_notification_and_button_are_translated(self):
        from nexcora_studio.bot.sender import AiogramSender
        from nexcora_studio.outbox import Notification
        sink = LanguageSink()
        bot = Bot(BOT_TOKEN, session=sink)
        try:
            for locale, body, button in [('en', 'The result is ready for review', 'Open project'),
                                         ('kk', 'Нәтиже қабылдауға жіберілді', 'Жобаны ашу')]:
                await AiogramSender(bot).send(Notification(9, 2, 101, 'deliver',
                    'https://studio.test/projects/2', language_code=locale))
                self.assertIn(body, sink.messages[-1].text)
                self.assertEqual(sink.messages[-1].reply_markup.inline_keyboard[0][0].text, button)
        finally:
            await bot.session.close()


if __name__ == '__main__': unittest.main()
