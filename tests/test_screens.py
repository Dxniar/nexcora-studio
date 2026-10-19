import html
from aiogram import Bot
from aiogram.methods import SendMessage, EditMessageText, AnswerCallbackQuery
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery, User, Chat, InaccessibleMessage
from orderbot.config import Config
from repo_helpers import RepoCase
from telegram_stub import RecordingSession


class ScreenTests(RepoCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.session=RecordingSession()
        self.bot=Bot('123456:TEST',session=self.session)
        self.config=Config('123456:TEST',999,self.path)

    async def asyncTearDown(self): await self.bot.session.close()

    async def test_home_payloads_and_maximum_unicode(self):
        from orderbot.presentation import render_home,render_confirmation
        from orderbot.callbacks import decode_action
        from dataclasses import replace
        for owner in (True,False):
            screen=render_home(self.config,is_admin=owner,has_draft=True)
            buttons=[b for row in screen.keyboard.inline_keyboard for b in row]
            self.assertEqual(any('Кабинет' in b.text for b in buttons),owner)
            for b in buttons:
                self.assertLessEqual(len(b.callback_data.encode()),64)
                self.assertIsNotNone(decode_action(b.callback_data))
        draft=replace(await self.completed_draft(),description='😀'*2000,name='<'*80,budget='&'*80,deadline='>'*80)
        screen=render_confirmation(draft,username=None,config=self.config)
        self.assertGreater(len(screen.parts),1)
        text=''.join(html.unescape(p.replace('<b>','').replace('</b>','')) for p in screen.parts)
        self.assertEqual(text.count('😀'),2000)
        for part in screen.parts:
            self.assertLessEqual(len(html.unescape(part).encode('utf-16-le'))//2,3500)
        self.assertIn('&lt;', ''.join(screen.parts))
        for data in (None,'x'*100,'garbage','d|not-an-id|0|s|','n|home|bad|g|'):
            self.assertIsNone(decode_action(data))

    async def test_unavailable_edit_and_unchanged_callback(self):
        from orderbot.presentation import render_home
        from orderbot.screens import show_screen
        screen=render_home(self.config,is_admin=False,has_draft=False)
        source=InaccessibleMessage(chat=Chat(id=123,type='private'),message_id=88,date=0)
        for index,kind in enumerate(('inaccessible','missing','unchanged')):
            if kind!='inaccessible':
                source=await self.bot.send_message(123,'old')
                self.session.fail_next(EditMessageText,lambda m: TelegramBadRequest(method=m,message='message is not modified' if kind=='unchanged' else 'message to edit not found'))
            before=len(self.session.sent)
            query=CallbackQuery(id=str(index),from_user=User(id=123,is_bot=False,first_name='Client'),chat_instance='test',message=source,data='ignored').as_(self.bot)
            await show_screen(query,screen)
            self.assertEqual(len(self.session.sent)-before,0 if kind=='unchanged' else 1)
            self.assertEqual([m.callback_query_id for m in self.session.calls_of(AnswerCallbackQuery)].count(str(index)),1)

    async def test_owner_notification_is_safe_for_long_input(self):
        from dataclasses import replace
        from orderbot.drafts import DraftService
        from orderbot.notifications import NotificationService
        draft=replace(await self.completed_draft(),description='😀'*2000)
        draft=await self.repo.update_draft(draft,expected_revision=draft.revision)
        await DraftService(self.repo).submit(123,draft.id,draft.revision,username=None,admin_id=999)
        await NotificationService(self.repo,self.bot,self.config).deliver_due_once()
        sends=self.session.calls_of(SendMessage,chat_id=999)
        self.assertGreater(len(sends),1)
        for message in sends:
            self.assertLessEqual(len(html.unescape(message.text).encode('utf-16-le'))//2,3500)
