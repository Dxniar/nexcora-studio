"""The only Telegram sending adapter used by the outbox."""
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter, TelegramServerError
from ..outbox import DeliveryFailure
from ..i18n import normalize_language, notification_event, translate
from .handlers import app_keyboard


class AiogramSender:
    def __init__(self, bot): self.bot = bot

    async def send(self, notification):
        language = normalize_language(notification.language_code)
        text = translate('notification.body', language, project_id=notification.project_id,
                         event=notification_event(notification.kind, language))
        try:
            message = await self.bot.send_message(notification.recipient_id, text,
                reply_markup=app_keyboard(notification.url, label=translate('notification.open', language)), request_timeout=20)
        except TelegramRetryAfter as exc:
            raise DeliveryFailure('retry_after', retry_after=exc.retry_after) from None
        except (TelegramNetworkError, TelegramServerError):
            raise DeliveryFailure('temporary') from None
        except TelegramForbiddenError:
            raise DeliveryFailure('forbidden', permanent=True) from None
        except TelegramBadRequest:
            raise DeliveryFailure('telegram_rejected', permanent=True) from None
        except TelegramAPIError:
            raise DeliveryFailure('telegram_rejected', permanent=True) from None
        return message.message_id
