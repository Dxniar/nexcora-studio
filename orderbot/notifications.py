"""Доставка очереди: временные сбои переживают перезапуск."""
import asyncio
import logging
from aiogram.exceptions import (TelegramAPIError, TelegramRetryAfter,
                                TelegramNetworkError, TelegramServerError)
from .presentation import render_notification

logger = logging.getLogger(__name__)
DELAYS = (10,60,300,1800)


class NotificationService:
    def __init__(self, repo, bot, config):
        self.repo, self.bot, self.config = repo,bot,config

    async def deliver_due_once(self, *, limit=20):
        processed = 0
        for _ in range(limit):
            event = await self.repo.claim_notification(self.config.admin_id)
            if event is None: break
            processed += 1
            payload = await self.repo.notification_payload(event.id,self.config.admin_id)
            if payload is None: continue
            event,order = payload
            screen = render_notification(event,order,self.config)
            try:
                for index,part in enumerate(screen.parts):
                    message = await self.bot.send_message(event.recipient_id,part,parse_mode='HTML',
                        reply_markup=screen.keyboard if index==len(screen.parts)-1 else None,request_timeout=12)
            except TelegramRetryAfter as error:
                await self.repo.record_failure(event.id,permanent=False,next_attempt_at=self.repo.clock()+max(1,error.retry_after),error_code='retry_after')
            except (TelegramNetworkError,TelegramServerError):
                await self.repo.record_failure(event.id,permanent=False,next_attempt_at=self.repo.clock()+DELAYS[min(event.attempts-1,3)],error_code='temporary')
            except TelegramAPIError as error:
                logger.warning('Notification %s: %s',event.id,type(error).__name__)
                await self.repo.record_failure(event.id,permanent=True,next_attempt_at=None,error_code=type(error).__name__)
            else:
                await self.repo.record_sent(event.id,message.message_id)
        return processed

    async def run(self, stop_event):
        await self.repo.recover_notifications()
        while not stop_event.is_set():
            await self.deliver_due_once()
            try: await asyncio.wait_for(stop_event.wait(),timeout=1)
            except asyncio.TimeoutError: pass
