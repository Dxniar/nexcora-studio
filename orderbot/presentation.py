"""Тексты заявок и безопасные ссылки Telegram."""
from html import escape
from dataclasses import dataclass
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from . import keyboards as kb
from .catalog import get_service
from .models import STATUSES


@dataclass(frozen=True)
class Screen:
    parts: tuple[str, ...]
    keyboard: InlineKeyboardMarkup | None = None


def text_screen(title, body, keyboard=None):
    chunks=[]
    start=0
    units=0
    for i,char in enumerate(body):
        size=2 if ord(char)>0xffff else 1
        if units+size>3200:
            chunks.append(body[start:i]); start=i; units=0
        units+=size
    chunks.append(body[start:])
    parts=tuple(f'<b>{escape(title)}</b>\n\n{escape(chunk)}' for chunk in chunks)
    return Screen(parts,keyboard)


def render_home(config, *, is_admin, has_draft):
    return text_screen('NEXCORA', 'Разработка под вашу задачу\n\nВыберите услугу или расскажите, что хотите сделать.\nСтоимость и сроки обсудим после уточнения задачи.',
                       kb.home_keyboard(is_admin=is_admin,has_draft=has_draft))


def render_service(service_id, config):
    item=get_service(service_id)
    if item is None: raise ValueError('Unknown service')
    return text_screen(item.title,item.summary+'\n\nЧто можно обсудить:\n'+'\n'.join('• '+e for e in item.examples)+'\n\nВозможность реализации, стоимость и срок зависят от задачи.',
                       kb.markup([kb.button('🚀 Обсудить такую задачу','service',item.id,verb='start')],
                                 [kb.button('‹ Все услуги','nav','services'),kb.home_button()]))


def draft_body(draft):
    item=get_service(draft.service_id)
    return (f"Услуга: {item.title if item else 'не выбрана'}\n\nЗадача: {draft.description}\n\n"
            f"Бюджет: {draft.budget or 'обсудим'}\nЖелаемый срок: {draft.deadline or 'не указан'}\nИмя: {draft.name}")


def render_confirmation(draft, *, username, config):
    contact = (f'Связь: @{username}' if username else
               f'У вас нет Telegram username. Напишите владельцу сами: @{config.owner_username}. Ссылка на профиль по ID может быть недоступна.')
    body=draft_body(draft)+'\n\n'+contact+'\n\nПри отправке имя, задача и Telegram-контакт будут переданы владельцу. Изменения статуса можно получать здесь. Удаление данных: /delete_my_data.'
    return text_screen('Проверьте заявку',body,kb.draft_keyboard(draft))


def render_draft(draft, *, username, config):
    if draft.step=='confirm': return render_confirmation(draft,username=username,config=config)
    prompts={'service':('Выберите услугу','Какую задачу хотите обсудить?'),
             'description':('Расскажите о задаче','Что должно получиться? Кто будет пользоваться результатом?\nОт 10 до 2000 символов.'),
             'budget':('Ориентир по бюджету','Укажите удобный бюджет и валюту. До 80 символов.\nМожно выбрать «Пока не знаю».'),
             'deadline':('Желаемый срок','Когда хотелось бы получить результат? До 80 символов.\nЭто пожелание, окончательный срок обсудим лично.'),
             'name':('Как к вам обращаться?','Введите имя от 2 до 80 символов.')}
    title,body=prompts[draft.step]
    body+='\n\nЧерновик сохраняется, чтобы вы могли продолжить позже. Владелец увидит заявку после отправки. Удаление: /delete_my_data.'
    return text_screen(title,body,kb.draft_keyboard(draft))


def render_order(order, *, audience, config):
    body=(f"Статус: {STATUSES.get(order.get('status'),'Получена')}\nУслуга: {order['service']}\n"
          f"Дата (UTC): {order.get('created_at','')}\n\nЗадача: {order['comment']}\n\n"
          f"Бюджет: {order.get('budget') or 'обсудим'}\nЖелаемый срок: {order.get('deadline') or 'не указан'}\nИмя: {order['client_name']}")
    rows=[]
    if audience=='admin':
        body+=f"\nTelegram ID: {order['telegram_user_id']}"
        if order.get('phone'): body+=f"\nТелефон (старая заявка): {order['phone']}"
        if not order.get('username'): body+='\nУ клиента нет username: ссылка по ID может быть недоступна.'
        rows.append([InlineKeyboardButton(text='💬 Открыть контакт клиента',url=contact_link(order['telegram_user_id'],order.get('username')))])
        rows.extend(kb.status_keyboard(order))
        rows.append([kb.button('‹ К заявкам','admin',0,verb='list',argument='all'),kb.client_menu_button()])
    else:
        rows.append([InlineKeyboardButton(text='💬 Написать владельцу',url=f'https://t.me/{config.owner_username}')])
        rows.append([kb.button('‹ Мои заявки','nav','myorders'),kb.home_button()])
    return text_screen(f"Заявка №{order['id']}",body,kb.markup(*rows))


def render_notification(event, order, config):
    if event.kind=='new_order': return render_order(order,audience='admin',config=config)
    return text_screen(f"Заявка №{order['id']}",f"Новый статус: {STATUSES[order['status']]}",
                       kb.markup([kb.button('📋 Открыть заявку','order',order['id'],verb='view')]))


def contact_link(user_id: int, username: str | None) -> str:
    if username:
        return f"https://t.me/{escape(username, quote=True)}"
    return f"tg://user?id={int(user_id)}"


def format_order(order: dict) -> str:
    link = contact_link(order['telegram_user_id'], order.get('username'))
    label = '@' + order['username'] if order.get('username') else 'Профиль клиента'
    lines = [
        f"Заявка №{order['id']}",
        f"Услуга: {escape(order['service'])}",
        f"Имя: {escape(order['client_name'])}",
        f"Задача: {escape(order['comment'])}",
        f'<a href="{link}">{escape(label)}</a>',
        f"Telegram ID: {order['telegram_user_id']}",
    ]
    if order.get('phone'):
        lines.append(f"Телефон (старая заявка): {escape(order['phone'])}")
    if order.get('created_at'):
        lines.append(f"Время (UTC): {escape(order['created_at'])}")
    return '\n'.join(lines)
