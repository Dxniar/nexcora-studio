"""Обновление экранов без дублирования неизменившихся сообщений."""
from aiogram.types import CallbackQuery, Message
from aiogram.exceptions import TelegramBadRequest


async def show_screen(event, screen):
    if isinstance(event,CallbackQuery):
        try: await event.answer()
        except TelegramBadRequest: pass
        source=event.message
        if isinstance(source,Message) and len(screen.parts)==1:
            try:
                await source.edit_text(screen.parts[0],parse_mode='HTML',reply_markup=screen.keyboard)
                return
            except TelegramBadRequest as error:
                detail=error.message.lower()
                if 'message is not modified' in detail: return
                if 'not found' not in detail and "can't be edited" not in detail and 'cannot be edited' not in detail: raise
        chat_id=source.chat.id if source else event.from_user.id
        for index,part in enumerate(screen.parts):
            await event.bot.send_message(chat_id,part,parse_mode='HTML',reply_markup=screen.keyboard if index==len(screen.parts)-1 else None)
    else:
        for index,part in enumerate(screen.parts):
            await event.answer(part,parse_mode='HTML',reply_markup=screen.keyboard if index==len(screen.parts)-1 else None)
