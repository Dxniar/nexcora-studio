from datetime import datetime, timezone
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendMessage, EditMessageText, AnswerCallbackQuery, DeleteMessage
from aiogram.types import Chat, Message, User, InlineKeyboardMarkup
from aiogram.exceptions import TelegramBadRequest


class RecordingSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.requests, self.sent, self.messages, self.failures = [], [], {}, []
        self.next_id = 0

    async def close(self): pass

    async def stream_content(self, *args, **kwargs):
        if False: yield b''

    def fail_next(self, method_type, exception_factory, *, chat_id=None, message_id=None, times=1):
        self.failures.append([method_type,exception_factory,chat_id,message_id,times])

    def calls_of(self, method_type, *, chat_id=None):
        return [m for m in self.requests if isinstance(m,method_type)
                and (chat_id is None or getattr(m,'chat_id',None)==chat_id)]

    def last_message(self, chat_id):
        return next(m for (chat,_),m in reversed(self.messages.items()) if chat==chat_id)

    async def make_request(self, bot, method, timeout=None):
        self.requests.append(method)
        for rule in list(self.failures):
            cls,factory,chat_id,message_id,_ = rule
            if (isinstance(method,cls) and (chat_id is None or getattr(method,'chat_id',None)==chat_id)
                    and (message_id is None or getattr(method,'message_id',None)==message_id)):
                rule[4] -= 1
                if not rule[4]: self.failures.remove(rule)
                raise factory(method)
        if isinstance(method,SendMessage):
            self.next_id += 1
            self.sent.append(method)
            msg = Message(message_id=self.next_id,date=datetime.now(timezone.utc),
                          chat=Chat(id=int(method.chat_id),type='private'),
                          from_user=User(id=bot.id,is_bot=True,first_name='Nexcora'),text=method.text,
                          reply_markup=method.reply_markup if isinstance(method.reply_markup,InlineKeyboardMarkup) else None).as_(bot)
            self.messages[(msg.chat.id,msg.message_id)] = msg
            return msg
        if isinstance(method,EditMessageText):
            key = (int(method.chat_id),method.message_id)
            if key not in self.messages:
                raise TelegramBadRequest(method=method,message='message to edit not found')
            msg = self.messages[key].model_copy(update={'text':method.text,'reply_markup':method.reply_markup}).as_(bot)
            self.messages.pop(key)
            self.messages[key] = msg
            return msg
        if isinstance(method,DeleteMessage):
            self.messages.pop((int(method.chat_id),method.message_id),None)
            return True
        if isinstance(method,AnswerCallbackQuery): return True
        raise AssertionError(type(method))
