from aiogram import Router,F
from aiogram.filters import Command
from . import keyboards as kb,views
from .callbacks import decode_action
from .models import InvalidInput,NotFound
from .repository import require_admin
from .presentation import text_screen,render_order
from .screens import show_screen


async def listing(event,config,repo,*,page=0,status=None):
    await views.admin_orders(event,config,repo,page=page,status=status)


async def orders(message,config,repo): await listing(message,config,repo)


async def failures(event,config,repo,page=0,note=''):
    rows,total=await repo.list_owner_failures(event.from_user.id,config.admin_id,page=page)
    buttons=[]
    lines=[note] if note else []
    lines.append(f'Требуют внимания: {total}')
    for item in rows:
        label='владельцу' if item.kind=='new_order' else 'клиенту'
        lines.append(f'Заявка №{item.order_id} · {label} · попыток: {item.attempts}')
        buttons.append([kb.button(f'Открыть заявку №{item.order_id}','admin',item.order_id,verb='view')])
        if item.kind=='new_order':
            buttons.append([kb.button(f'Повторить владельцу №{item.order_id}','retry',item.id,verb='set')])
    pager=[]
    if page: pager.append(kb.button('‹ Назад','admin',page-1,verb='failures'))
    if (page+1)*5<total: pager.append(kb.button('Далее ›','admin',page+1,verb='failures'))
    buttons.extend([pager,[kb.button('‹ Кабинет','admin',0,verb='list',argument='all'),kb.client_menu_button()]])
    lines.append('Блокировки и отключённые уведомления клиента не возобновляются автоматически.')
    await show_screen(event,text_screen('Недоставленные уведомления','\n\n'.join(lines),kb.markup(*buttons)))


async def action(query,config,repo):
    require_admin(query.from_user.id,config.admin_id)
    value=decode_action(query.data)
    if value is None: raise InvalidInput()
    if value.verb=='list': return await listing(query,config,repo,page=int(value.entity_id),status=None if value.argument=='all' else value.argument)
    if value.verb=='failures': return await failures(query,config,repo,int(value.entity_id))
    if value.verb=='set':
        row=await repo.change_status(query.from_user.id,config.admin_id,int(value.entity_id),value.revision,value.argument)
    else: row=await repo.get_admin_order(query.from_user.id,config.admin_id,int(value.entity_id))
    if row is None: raise NotFound()
    await show_screen(query,render_order(row,audience='admin',config=config))


async def retry(query,config,repo):
    require_admin(query.from_user.id,config.admin_id)
    value=decode_action(query.data)
    if value is None: raise InvalidInput()
    queued=await repo.retry_owner_event(query.from_user.id,config.admin_id,int(value.entity_id))
    await failures(query,config,repo,note='Повтор поставлен в очередь.' if queued else 'Это уведомление уже обработано или недоступно для повтора.')


def create_router():
    router=Router()
    router.message.register(orders,Command('orders'))
    router.callback_query.register(action,F.data.startswith('a|'))
    router.callback_query.register(retry,F.data.startswith('r|'))
    return router
