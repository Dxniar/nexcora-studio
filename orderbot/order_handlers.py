from aiogram import Router,F
from aiogram.filters import Command
from .callbacks import decode_action
from . import views,keyboards as kb
from .models import NotFound,InvalidInput
from .presentation import text_screen,render_order
from .screens import show_screen


async def my_orders(message,config,repo): await views.my_orders(message,config,repo)
async def delete_prompt(message,config,repo): await views.delete_prompt(message,config,repo)


async def order(query,config,repo):
    action=decode_action(query.data)
    if action is None: raise InvalidInput()
    row=await repo.get_user_order(query.from_user.id,int(action.entity_id))
    if row is None: raise NotFound()
    await show_screen(query,render_order(row,audience='client',config=config))


async def preferences(query,config,repo):
    action=decode_action(query.data)
    if action is None: raise InvalidInput()
    await repo.set_notifications_enabled(query.from_user.id,action.entity_id=='1',expected_revision=action.revision)
    await views.my_orders(query,config,repo)


async def delete(query,config,repo):
    action=decode_action(query.data)
    if action is None: raise InvalidInput()
    if action.verb=='keep':
        await repo.cancel_delete(query.from_user.id,action.entity_id)
        return await views.home(query,config,repo)
    result=await repo.delete_user_data(query.from_user.id,action.entity_id)
    await show_screen(query,text_screen('Данные удалены',f'Удалены ваши заявки: {result.orders}, черновики: {result.drafts}.\nУже отправленные сообщения Telegram и резервные копии остались.',kb.markup([kb.home_button()])))


def create_router():
    router=Router()
    router.message.register(my_orders,Command('myorders'))
    router.message.register(delete_prompt,Command('delete_my_data'))
    router.callback_query.register(order,F.data.startswith('o|'))
    router.callback_query.register(preferences,F.data.startswith('p|'))
    router.callback_query.register(delete,F.data.startswith('x|'))
    return router
