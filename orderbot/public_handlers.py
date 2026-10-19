from aiogram import Router,F
from aiogram.filters import Command,CommandStart
from aiogram.types import InlineKeyboardButton,ReplyKeyboardRemove
from .callbacks import decode_action
from . import keyboards as kb,views
from .catalog import SERVICES
from .models import InvalidInput
from .presentation import text_screen,render_service
from .screens import show_screen


async def start(message,config,repo):
    await message.answer('Добро пожаловать в Nexcora.',reply_markup=ReplyKeyboardRemove())
    await views.entry(message,config,repo)


async def public_page(event,config,repo,page):
    if page=='home': return await views.home(event,config,repo)
    if page=='new': return await views.begin(event,config,repo)
    if page=='resume': return await views.resume(event,config,repo)
    if page=='myorders': return await views.my_orders(event,config,repo)
    if page=='delete': return await views.delete_prompt(event,config,repo)
    if page=='services':
        screen=text_screen('Услуги','Выберите направление. Возможность реализации, стоимость и срок обсудим по вашей задаче.',
                           kb.markup(*[[kb.button(s.title,'service',s.id,verb='view')] for s in SERVICES],[kb.home_button()]))
    elif page=='projects':
        screen=text_screen('Проекты · Nexcora',
            'Демонстрационный проект\n\nTelegram-бот для обсуждения задач и приёма заявок. Клиент заполняет анкету, проверяет данные и видит статус. Владелец обрабатывает заявки в своём кабинете.\n\nPython · aiogram · SQLite\n\nЭто демонстрация возможностей проекта. Коммерческие результаты и отзывы не заявляются.',
            kb.markup([kb.button('🚀 Обсудить похожую задачу','service','bot',verb='start')],[kb.home_button()]))
    elif page=='workflow':
        screen=text_screen('Как проходит работа',
            '1. Вы описываете задачу.\n2. Обсуждаем возможность, объём, стоимость и срок.\n3. Согласовываем условия.\n4. Выполнение задачи.\n5. Передача результата.\n\nБюджет и срок в анкете — ваши пожелания для обсуждения.',
            kb.markup([kb.button('🚀 Обсудить проект','nav','new')],[kb.home_button()]))
    elif page=='contact':
        screen=text_screen('Связаться с владельцем',f'Напишите Данияру: @{config.owner_username}\n\nЕсли у вас нет username, начните личный диалог сами — так владелец сможет ответить.',
            kb.markup([InlineKeyboardButton(text='💬 Написать Данияру',url=f'https://t.me/{config.owner_username}')],[kb.home_button()]))
    elif page=='help':
        screen=text_screen('Помощь',
            '/start — главное меню\n/new — новая заявка\n/menu — вернуться в меню\n/cancel — удалить черновик\n/myorders — мои заявки\n/myid — Telegram ID\n/delete_my_data — удаление данных\n\nГлавное меню сохраняет незавершённую анкету.',kb.markup([kb.home_button()]))
    else: raise InvalidInput()
    await show_screen(event,screen)


async def nav(query,config,repo):
    action=decode_action(query.data)
    if action is None: raise InvalidInput()
    if action.entity_id=='myorders': return await views.my_orders(query,config,repo,int(action.argument or 0))
    await public_page(query,config,repo,action.entity_id)


async def service(query,config,repo):
    action=decode_action(query.data)
    if action is None: raise InvalidInput()
    if action.verb=='start': return await views.begin(query,config,repo,action.entity_id)
    await show_screen(query,render_service(action.entity_id,config))


async def menu(message,config,repo): await views.entry(message,config,repo)
async def help_page(message,config,repo): await public_page(message,config,repo,'help')
async def my_id(message): await show_screen(message,text_screen('Ваш Telegram ID',str(message.from_user.id),kb.markup([kb.home_button()])))


async def legacy_menu(message,config,repo):
    await public_page(message,config,repo,{'Мои услуги':'services','Связаться со мной':'contact','Оставить заявку':'new'}[message.text])


def create_router():
    router=Router()
    router.message.register(start,CommandStart())
    router.message.register(menu,Command('menu'))
    router.message.register(help_page,Command('help'))
    router.message.register(my_id,Command('myid'))
    router.message.register(legacy_menu,F.text.in_(('Мои услуги','Связаться со мной','Оставить заявку')))
    router.callback_query.register(nav,F.data.startswith('n|'))
    router.callback_query.register(service,F.data.startswith('s|'))
    return router
