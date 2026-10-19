from datetime import datetime, timezone
from aiogram import Bot
from aiogram.types import Message,Chat,User,Update,CallbackQuery
from orderbot.__main__ import create_dispatcher
from orderbot.config import Config
from orderbot.repository import Repository
from orderbot.notifications import NotificationService
from repo_helpers import RepoCase
from telegram_stub import RecordingSession


class UiCase(RepoCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.config=Config('123456:TEST',999,self.path)
        self.session=RecordingSession()
        self.bot=Bot(self.config.bot_token,session=self.session)
        self.dp=create_dispatcher()
        self.counter=0

    async def asyncTearDown(self):
        await self.dp.fsm.close()
        await self.bot.session.close()

    async def say(self,text=None,*,user_id=123,username='client_user',chat_id=None,chat_type='private'):
        self.counter+=1
        message=Message(message_id=10000+self.counter,date=datetime.now(timezone.utc),
                        chat=Chat(id=chat_id or user_id,type=chat_type),
                        from_user=User(id=user_id,is_bot=False,first_name='Client',username=username),text=text)
        await self.dp.feed_update(self.bot,Update(update_id=self.counter,message=message),config=self.config,repo=self.repo)

    async def click(self,data,*,user_id=123,username='client_user',source=None,chat_id=None,chat_type='private',callback_id=None):
        self.counter+=1
        if source is None: source=self.session.last_message(user_id)
        if chat_id is not None: source=source.model_copy(update={'chat':Chat(id=chat_id,type=chat_type)})
        callback_id=callback_id or f'click-{self.counter}'
        query=CallbackQuery(id=callback_id,from_user=User(id=user_id,is_bot=False,first_name='Client',username=username),
                            chat_instance='test',message=source,data=data)
        await self.dp.feed_update(self.bot,Update(update_id=self.counter,callback_query=query),config=self.config,repo=self.repo)
        return callback_id

    def button_data(self,screen,label):
        for row in screen.reply_markup.inline_keyboard:
            for button in row:
                if label in button.text and button.callback_data: return button.callback_data
        raise AssertionError('Missing button: '+label)

    async def press(self,label,*,user_id=123,username='client_user'):
        source=self.session.last_message(user_id)
        return await self.click(self.button_data(source,label),user_id=user_id,username=username,source=source)

    async def restart_dispatcher(self):
        await self.dp.fsm.close()
        self.dp=create_dispatcher()
        self.repo=Repository(self.path,clock=self.clock)

    async def draft(self,*,username='client_user',description='Нужен Telegram-бот для заявок',name='Айша',budget=None,desired_deadline=None):
        await self.say('/new',username=username)
        if await self.repo.get_draft(123) and 'Начать заново' in (self.session.last_message(123).text or ''):
            await self.press('Начать заново',username=username)
        await self.press('Telegram-бот',username=username)
        await self.say(description,username=username)
        if budget is None: await self.press('Пока не знаю',username=username)
        else: await self.say(budget,username=username)
        if desired_deadline is None: await self.press('Пропустить',username=username)
        else: await self.say(desired_deadline,username=username)
        await self.say(name,username=username)
        return self.session.last_message(123)

    async def deliver(self):
        return await NotificationService(self.repo,self.bot,self.config).deliver_due_once()

    def client_text(self,user_id=123):
        return '\n'.join(m.text or '' for (chat,_),m in self.session.messages.items() if chat==user_id)
