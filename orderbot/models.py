"""Типы сценария заявки и ожидаемые ошибки операций."""
from dataclasses import dataclass
from typing import TypedDict

STATUSES = {'new': 'Получена', 'discussing': 'Обсуждаем', 'in_progress': 'В работе',
            'completed': 'Завершена', 'closed': 'Закрыта'}
TRANSITIONS = {'new': ('discussing', 'in_progress', 'closed'),
               'discussing': ('in_progress', 'closed'),
               'in_progress': ('discussing', 'completed', 'closed'),
               'completed': ('discussing',), 'closed': ('discussing',)}


class NotFound(Exception): pass
class Conflict(Exception): pass
class InvalidInput(Exception): pass
class AccessDenied(Exception): pass


class Cooldown(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__('Повторите позже')


@dataclass(frozen=True)
class Draft:
    id: str
    user_id: int
    service_id: str | None = None
    description: str = ''
    budget: str = ''
    deadline: str = ''
    name: str = ''
    step: str = 'service'
    return_to_confirm: bool = False
    revision: int = 0
    updated_at: float = 0


class OrderRecord(TypedDict):
    id: int
    telegram_user_id: int
    username: str | None
    service: str
    client_name: str
    phone: str
    comment: str
    created_at: str
    draft_id: str | None
    budget: str
    deadline: str
    status: str
    status_version: int


@dataclass(frozen=True)
class OrderPage:
    items: list[OrderRecord]
    page: int
    total: int


@dataclass(frozen=True)
class Submission:
    order: OrderRecord
    created: bool


@dataclass(frozen=True)
class DeleteResult:
    orders: int
    drafts: int
    notifications: int


@dataclass(frozen=True)
class OutboxEvent:
    id: int
    event_key: str
    kind: str
    order_id: int
    recipient_id: int
    status_value: str | None
    status_version: int | None
    state: str
    attempts: int
    next_attempt_at: float
    message_id: int | None
    error_code: str | None
