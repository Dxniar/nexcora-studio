"""Сборка маршрутов, защита личных чатов и безопасные ответы об ошибках."""
import logging
import sqlite3
from aiogram import Router,F,BaseMiddleware
from aiogram.types import CallbackQuery
from aiogram.exceptions import TelegramAPIError
from . import public_handlers,form_handlers,order_handlers,admin_handlers,keyboards as kb
from .callbacks import decode_action
from .models import AccessDenied,Conflict,NotFound,InvalidInput,Cooldown
from .presentation import text_screen,render_draft,render_order
from .screens import show_screen

logger=logging.getLogger(__name__)


class SafeMiddleware(BaseMiddleware):
    async def __call__(self,handler,event,data):
        if isinstance(event,CallbackQuery):
            if (event.message is None or event.message.chat.type!='private'
                    or event.message.chat.id!=event.from_user.id):
                try: await event.answer('Откройте бота в личном чате.')
                except TelegramAPIError: pass
                return
        try:
            return await handler(event,data)
        except AccessDenied:
            screen=text_screen('Доступ ограничен','Эта команда доступна только администратору.',kb.markup([kb.home_button()]))
        except Cooldown as error:
            screen=text_screen('Немного подождите',f'Попробуйте отправить новую заявку через {error.retry_after} сек. Черновик сохранён.',kb.markup([kb.button('Продолжить заявку','nav','resume'),kb.home_button()]))
        except (Conflict,InvalidInput) as error:
            screen=text_screen('Проверьте действие','Экран устарел или ввод не подходит. Откройте актуальный раздел и повторите действие.',kb.markup([kb.home_button()]))
            action=decode_action(event.data) if isinstance(event,CallbackQuery) else None
            if action and action.scope=='admin' and event.from_user.id==data['config'].admin_id:
                try:
                    row=await data['repo'].get_admin_order(event.from_user.id,data['config'].admin_id,int(action.entity_id))
                    if row: screen=render_order(row,audience='admin',config=data['config'])
                except (sqlite3.Error,OSError): pass
            if action is None or action.scope=='draft':
                try:
                    draft=await data['repo'].get_draft(event.from_user.id)
                    if draft:
                        current=render_draft(draft,username=event.from_user.username,config=data['config'])
                        from .presentation import Screen
                        screen=Screen(('Проверьте ввод или обновлённую анкету.\n\n'+current.parts[0],*current.parts[1:]),current.keyboard)
                except (sqlite3.Error,OSError): pass
        except NotFound:
            screen=text_screen('Запись недоступна','Заявка или черновик не найдены. Вернитесь в главное меню.',kb.markup([kb.home_button()]))
        except (sqlite3.Error,OSError) as error:
            logger.error('Operation failed: %s',type(error).__name__)
            screen=text_screen('Не удалось выполнить действие','Попробуйте ещё раз. Если ошибка повторится, напишите владельцу. Сохранённые данные остаются в базе.',kb.markup([kb.home_button()]))
        except TelegramAPIError as error:
            logger.warning('Screen delivery failed: %s',type(error).__name__)
            return
        try: await show_screen(event,screen)
        except TelegramAPIError as error: logger.warning('Error screen delivery failed: %s',type(error).__name__)


async def unknown_callback(query):
    await show_screen(query,text_screen('Кнопка устарела','Откройте актуальное меню.',kb.markup([kb.home_button()])))


def create_router():
    router=Router()
    router.message.filter(F.chat.type=='private')
    router.message.outer_middleware(SafeMiddleware())
    router.callback_query.outer_middleware(SafeMiddleware())
    router.include_router(public_handlers.create_router())
    router.include_router(order_handlers.create_router())
    router.include_router(admin_handlers.create_router())
    router.include_router(form_handlers.create_router())
    fallback=Router()
    fallback.callback_query.register(unknown_callback)
    router.include_router(fallback)
    return router


router=create_router()
