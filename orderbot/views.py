"""Связь экранов с данными; обработчики используют эти общие представления."""
from . import keyboards as kb
from .catalog import SERVICES
from .drafts import DraftService
from .models import NotFound,STATUSES
from .presentation import text_screen,render_home,render_draft
from .screens import show_screen


async def home(event,config,repo):
    draft=await repo.get_draft(event.from_user.id)
    await show_screen(event,render_home(config,is_admin=event.from_user.id==config.admin_id,has_draft=bool(draft)))


async def entry(event,config,repo):
    if event.from_user.id==config.admin_id:
        return await admin_orders(event,config,repo)
    await home(event,config,repo)


async def admin_orders(event,config,repo,*,page=0,status=None):
    actor=event.from_user.id
    summary=await repo.admin_summary(actor,config.admin_id)
    records=await repo.list_admin_orders(actor,config.admin_id,status=status,page=page)
    body=(f"Всего: {summary['all']}\nНовые: {summary['new']}\nОбсуждаем: {summary['discussing']}\n"
          f"В работе: {summary['in_progress']}\nЗавершены: {summary['completed']}\nЗакрыты: {summary['closed']}\n"
          f"Не доставлено: {summary['failed_notifications']}\n\n"
          f"Фильтр: {STATUSES[status] if status else 'Все'} · страница {page+1}\n")
    body+='Выберите заявку.' if records.items else 'В этом разделе заявок пока нет.'
    await show_screen(event,text_screen('Кабинет владельца',body,kb.admin_orders_keyboard(records,status)))


async def form(event,draft,config):
    await show_screen(event,render_draft(draft,username=event.from_user.username,config=config))


async def begin(event,config,repo,service_id=None):
    draft=await repo.get_draft(event.from_user.id)
    if draft:
        screen=text_screen('У вас есть черновик','Продолжить заполнение или начать заново? Новый черновик заменит прежний.',
            kb.markup([kb.draft_action(draft,'▶ Продолжить','resume')],
                      [kb.draft_action(draft,'Начать заново','replace',service_id or '')],[kb.home_button()]))
        await show_screen(event,screen)
    else:
        await form(event,await DraftService(repo).start(event.from_user.id,service_id),config)


async def resume(event,config,repo):
    draft=await repo.get_draft(event.from_user.id)
    if draft: await form(event,draft,config)
    else: await begin(event,config,repo)


async def my_orders(event,config,repo,page=0):
    user_id=event.from_user.id
    records=await repo.list_user_orders(user_id,page=page)
    enabled=await repo.get_notifications_enabled(user_id)
    revision=await repo.get_user_revision(user_id)
    body=(f'Всего заявок: {records.total}\nВыберите заявку, чтобы увидеть подробности.' if records.total else
          'Заявок пока нет. Расскажите о задаче — обсудим возможность реализации.')
    await show_screen(event,text_screen('Мои заявки',body,kb.user_orders_keyboard(records,notifications_enabled=enabled,revision=revision)))


async def delete_prompt(event,config,repo):
    token=await repo.prepare_delete(event.from_user.id)
    await show_screen(event,text_screen('Удалить ваши данные?',
        'Будут удалены ваши заявки, черновик и настройки из рабочей базы. Ранее отправленные сообщения Telegram и резервные копии останутся. Подтверждение действует 5 минут.',
        kb.markup([kb.button('Удалить мои данные','delete',token,verb='confirm')],
                  [kb.button('‹ Назад','delete',token,verb='keep')])) )
