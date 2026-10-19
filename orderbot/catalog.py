"""Каталог направлений: обсуждение возможностей без обещаний опыта."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Service:
    id: str
    title: str
    summary: str
    examples: tuple[str, ...]


SERVICES = (
    Service('bot', 'Telegram-бот', 'Поможем сформулировать сценарий вашего бота.',
            ('Меню и анкеты', 'Сбор заявок', 'Уведомления владельцу')),
    Service('parser', 'Парсер', 'Обсудим сбор доступных данных и нужный формат результата.',
            ('Список товаров', 'Таблица из открытых страниц', 'Проверка и очистка данных')),
    Service('api', 'API-интеграция', 'Обсудим обмен данными между выбранными сервисами.',
            ('Получение данных из API', 'Выгрузка в CSV или JSON', 'Проверка формата')),
    Service('other', 'Другая задача', 'Расскажите идею — обсудим возможность реализации.',
            ('Обработка файлов', 'Небольшая автоматизация', 'Другая задача на Python')),
)


def get_service(service_id: str) -> Service | None:
    return next((item for item in SERVICES if item.id == service_id), None)
