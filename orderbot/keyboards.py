from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from .callbacks import Action, encode_action
from .catalog import SERVICES
from .models import STATUSES, TRANSITIONS


def button(text, scope, entity='', revision=0, verb='go', argument=''):
    return InlineKeyboardButton(text=text,callback_data=encode_action(Action(scope,str(entity),revision,verb,argument)))


def markup(*rows): return InlineKeyboardMarkup(inline_keyboard=[list(row) for row in rows if row])


def home_button(): return button('⌂ Главное меню','nav','home')


def client_menu_button(): return button('👤 Клиентское меню','nav','home')


def home_keyboard(*,is_admin,has_draft):
    rows=[]
    if has_draft: rows.append([button('▶ Продолжить заявку','nav','resume')])
    rows.extend([[button('🚀 Обсудить проект','nav','new')],
                 [button('🧩 Услуги','nav','services'),button('💼 Проекты','nav','projects')],
                 [button('📋 Мои заявки','nav','myorders'),button('💬 Связаться','nav','contact')],
                 [button('❓ Как проходит работа','nav','workflow')]])
    if is_admin: rows.append([button('⚙ Кабинет владельца','admin',0,verb='list',argument='all')])
    return markup(*rows)


def draft_action(draft, text, verb, argument=''):
    return button(text,'draft',draft.id,draft.revision,verb,argument)


def draft_keyboard(draft):
    rows=[]
    if draft.step=='service':
        rows.extend([[draft_action(draft,s.title,'accept',s.id)] for s in SERVICES])
    elif draft.step=='confirm':
        rows.append([draft_action(draft,'✅ Отправить заявку','submit')])
        rows.extend([[draft_action(draft,label,'edit',field)] for field,label in
                     (('service','Изменить услугу'),('description','Изменить задачу'),
                      ('budget','Изменить бюджет'),('deadline','Изменить срок'),('name','Изменить имя'))])
    elif draft.step in ('budget','deadline'):
        rows.append([draft_action(draft,'Пока не знаю' if draft.step=='budget' else 'Пропустить','skip')])
    if draft.step not in ('service','confirm'):
        rows.append([draft_action(draft,'‹ Назад','back')])
    rows.append([home_button(),draft_action(draft,'Отменить заполнение','cancel')])
    return markup(*rows)


def user_orders_keyboard(page, *, notifications_enabled, revision):
    rows=[[button(f"№{o['id']} · {o['service'][:22]} · {o['created_at'][:10]} · {STATUSES.get(o['status'],'Получена')}",'order',o['id'],verb='view')] for o in page.items]
    pager=[]
    if page.page: pager.append(button('‹ Назад','nav','myorders',argument=str(page.page-1)))
    if (page.page+1)*5<page.total: pager.append(button('Далее ›','nav','myorders',argument=str(page.page+1)))
    rows.extend([pager,[button('🔔 Уведомления: включены' if notifications_enabled else '🔕 Уведомления: выключены',
                                'preferences',int(not notifications_enabled),revision,'set')],[home_button()]])
    return markup(*rows)


def admin_orders_keyboard(page, status):
    rows=[[button('📋 Все заявки','admin',0,verb='list',argument='all')],
          [button('🆕 Новые','admin',0,verb='list',argument='new'),button('🛠 В работе','admin',0,verb='list',argument='in_progress')],
          [button('💬 Обсуждаем','admin',0,verb='list',argument='discussing'),button('✅ Завершены','admin',0,verb='list',argument='completed')],
          [button('📁 Закрыты','admin',0,verb='list',argument='closed')]]
    rows.extend([[button(f"№{o['id']} · {o['client_name'][:18]} · {STATUSES.get(o['status'],'Получена')}",'admin',o['id'],verb='view')] for o in page.items])
    pager=[]
    if page.page: pager.append(button('‹ Назад','admin',page.page-1,verb='list',argument=status or 'all'))
    if (page.page+1)*5<page.total: pager.append(button('Далее ›','admin',page.page+1,verb='list',argument=status or 'all'))
    rows.append(pager)
    rows.extend([[button('⚠ Недоставленные уведомления','admin',0,verb='failures')],[client_menu_button()]])
    return markup(*rows)


def status_keyboard(order):
    return [[button(STATUSES[status],'admin',order['id'],order['status_version'],'set',status)]
            for status in TRANSITIONS.get(order['status'],())]
