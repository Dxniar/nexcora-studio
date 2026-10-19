"""Bot commands open the portal; API permissions remain server-side."""
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from ..i18n import LANGUAGES, normalize_language, translate


def app_keyboard(url, *, label=None, language='ru', include_language=False):
    rows = [[InlineKeyboardButton(text=label or translate('bot.open_app', language), web_app=WebAppInfo(url=url))]]
    if include_language:
        rows.append([InlineKeyboardButton(text=translate('bot.language', language), callback_data='language:choose')])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def language_keyboard(language='ru'):
    labels = {'ru': 'Русский', 'en': 'English', 'kk': 'Қазақша'}
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=('✓ ' if code == language else '') + labels[code], callback_data='language:' + code)
        for code in LANGUAGES
    ]])


def create_router(settings, database=None):
    router = Router(name='studio_commands')

    async def user_language(actor):
        language = normalize_language(actor.language_code)
        if database is None: return language
        from ..auth import TelegramIdentity, upsert_telegram_user
        async with database.session() as session:
            user = await upsert_telegram_user(session, database.engine.dialect.name,
                TelegramIdentity(actor.id, actor.first_name or '', actor.username, language))
            return normalize_language(user.language_code)

    @router.message(Command('start', 'menu', 'new', 'myorders', 'orders', 'help', 'myid', 'owner', 'language'))
    async def open_portal(message):
        if message.chat.type != 'private' or message.from_user is None:
            language = normalize_language(message.from_user.language_code if message.from_user else None)
            await message.answer(translate('bot.private_chat', language))
            return
        language = await user_language(message.from_user)
        owner = message.from_user.id == settings.admin_id
        command = message.text.split()[0].split('@')[0].removeprefix('/')
        if command == 'language':
            await message.answer(translate('bot.choose_language', language), reply_markup=language_keyboard(language))
            return
        route = '/owner' if owner else '/'
        if command in ('myorders', 'orders'): route = '/owner/projects' if owner else '/projects'
        elif command == 'new' and not owner: route = '/draft'
        text = translate('bot.owner' if owner else 'bot.portal', language)
        if command == 'myid': text = translate('bot.my_id', language, user_id=message.from_user.id)
        elif command == 'help': text = translate('bot.help', language)
        await message.answer(text, reply_markup=app_keyboard(settings.app_origin + route, language=language, include_language=True))

    @router.callback_query(F.data.startswith('language:'))
    async def choose_language(callback):
        actor = callback.from_user
        language = normalize_language(actor.language_code)
        # A group, inline or forwarded keyboard cannot persist a private preference.
        if callback.message is None or callback.message.chat.type != 'private' or callback.message.chat.id != actor.id:
            await callback.answer(translate('bot.private_chat', language), show_alert=True)
            return
        language = await user_language(actor)
        selection = callback.data.removeprefix('language:')
        if selection == 'choose':
            await callback.answer()
            await callback.bot.send_message(actor.id, translate('bot.choose_language', language), reply_markup=language_keyboard(language))
            return
        if selection not in LANGUAGES:
            await callback.answer(translate('bot.language_invalid', language), show_alert=True)
            return
        if database is not None:
            from ..auth import Principal
            from ..services.privacy import PrivacyService
            await PrivacyService(database, settings).set_language(Principal(actor.id, actor.id == settings.admin_id), selection)
        await callback.answer()
        route = '/owner' if actor.id == settings.admin_id else '/'
        await callback.bot.send_message(actor.id, translate('bot.language_saved', selection),
            reply_markup=app_keyboard(settings.app_origin + route, language=selection, include_language=True))

    return router
