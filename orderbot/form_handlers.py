from aiogram import Router,F
from aiogram.filters import Command
from . import views,keyboards as kb
from .callbacks import decode_action
from .drafts import DraftService
from .models import InvalidInput, STATUSES
from .presentation import text_screen
from .screens import show_screen


async def new(message,config,repo): await views.begin(message,config,repo)


async def cancel(message,config,repo):
    draft=await repo.get_draft(message.from_user.id)
    if draft: await repo.discard_draft(draft.user_id,draft.id,draft.revision)
    await show_screen(message,text_screen('Заполнение отменено','Черновик удалён. Отправленные заявки остаются в «Моих заявках».',kb.markup([kb.home_button()])))


async def submitted(event,result,config):
    order=result.order
    await show_screen(event,text_screen(f"Заявка №{order['id']} сохранена",
        f"Статус: {STATUSES[order['status']]}\nЗаявка доступна в «Моих заявках».\nДля личной связи: @{config.owner_username}",
        kb.markup([kb.button('📋 Открыть заявку','order',order['id'],verb='view')],[kb.home_button()])))


async def draft_action(query,config,repo):
    action=decode_action(query.data)
    if action is None: raise InvalidInput()
    user=query.from_user
    service=DraftService(repo)
    args=(user.id,action.entity_id,action.revision)
    if action.verb=='submit':
        return await submitted(query,await service.submit(*args,username=user.username,admin_id=config.admin_id),config)
    if action.verb=='replace':
        draft=await service.start(user.id,action.argument or None,replace=(action.entity_id,action.revision))
    elif action.verb=='cancel':
        await repo.discard_draft(*args)
        return await views.home(query,config,repo)
    elif action.verb=='resume': draft=await service.current(*args)
    elif action.verb=='accept': draft=await service.accept(*args,action.argument)
    elif action.verb=='skip': draft=await service.skip(*args)
    elif action.verb=='back': draft=await service.back(*args)
    elif action.verb=='edit': draft=await service.edit(*args,action.argument)
    else: raise InvalidInput()
    await views.form(query,draft,config)


async def text_input(message,config,repo):
    if message.text and message.text.startswith('/'):
        return await show_screen(message,text_screen('Неизвестная команда','Используйте /help или кнопки меню. Черновик сохранён.',kb.markup([kb.home_button()])))
    draft=await repo.get_draft(message.from_user.id)
    if draft is None: return await views.home(message,config,repo)
    service=DraftService(repo)
    if draft.step=='confirm':
        return await views.form(message,draft,config)
    draft=await service.accept(draft.user_id,draft.id,draft.revision,message.text)
    await views.form(message,draft,config)


def create_router():
    router=Router()
    router.message.register(new,Command('new'))
    router.message.register(cancel,Command('cancel'))
    router.message.register(cancel,F.text=='Отмена')
    router.callback_query.register(draft_action,F.data.startswith('d|'))
    router.message.register(text_input)
    return router
