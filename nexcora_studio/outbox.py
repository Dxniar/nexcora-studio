"""At-least-once Telegram delivery, with leases separate from business events.

A lost Telegram response can repeat a message after the lease expires. It can
never repeat the project operation which committed the event.
"""
import asyncio
from dataclasses import dataclass
from datetime import timedelta
import logging
from sqlalchemy import func, or_, select
from .auth import as_utc
from .errors import DomainError, not_found
from .i18n import normalize_language
from .models import Event, Outbox, Project, User, new_id, utcnow
from .services.common import integer

logger = logging.getLogger(__name__)
DELAYS = (10, 60, 300, 1800)
MAX_ATTEMPTS = 5
LEASE_SECONDS = 60


class DeliveryFailure(Exception):
    """Safe adapter result; never persists Telegram exception text or payloads."""
    def __init__(self, code='temporary', *, permanent=False, retry_after=None):
        allowed = {'temporary', 'timeout', 'retry_after', 'forbidden', 'chat_not_found', 'telegram_rejected'}
        self.code = code if code in allowed else 'temporary'
        self.permanent, self.retry_after = permanent, retry_after
        super().__init__(self.code)


@dataclass(frozen=True, slots=True)
class Notification:
    id: int
    project_id: int
    recipient_id: int
    kind: str
    url: str
    language_code: str = 'ru'


def _invalid_reason(row, project, user, settings, event):
    if row.legacy_event_key is not None: return 'legacy_event'
    if project is None or user is None: return 'project_missing'
    if event is None or event.project_id != project.id or event.kind != row.kind: return 'event_missing'
    if project.version != row.project_version: return 'stale_version'
    if row.recipient_role == 'owner':
        if row.recipient_id != settings.admin_id: return 'owner_changed'
    elif row.recipient_role == 'client':
        if row.recipient_id != project.user_id: return 'recipient_changed'
        if not user.notifications_enabled: return 'opted_out'
    else: return 'invalid_recipient'
    return None


async def _context(session, row_id):
    """Use the same user -> project -> outbox order as business/privacy writes."""
    project_id = await session.scalar(select(Outbox.project_id).where(Outbox.id == row_id))
    if project_id is None: return None, None, None, None
    user_id = await session.scalar(select(Project.user_id).where(Project.id == project_id))
    user = await session.scalar(select(User).where(User.id == user_id).with_for_update()) if user_id else None
    project = await session.scalar(select(Project).where(Project.id == project_id).with_for_update())
    row = await session.scalar(select(Outbox).where(Outbox.id == row_id).with_for_update())
    event = await session.get(Event, row.event_id) if row and row.event_id is not None else None
    return row, project, user, event


def _release(row):
    row.worker_id, row.lease_until = None, None


def _dto(row):
    return {key: getattr(row, key) for key in ('id', 'project_id', 'kind', 'recipient_role', 'state', 'attempts', 'error_code', 'project_version')} | {
        'next_attempt_at': as_utc(row.next_attempt_at).isoformat(),
    }


class OutboxService:
    def __init__(self, database, settings, *, clock=utcnow):
        self.db, self.settings, self.clock = database, settings, clock

    def _owner(self, principal):
        # An old principal or a forged role flag cannot survive an ADMIN_ID rotation.
        if not principal.is_owner or principal.user_id != self.settings.admin_id:
            raise DomainError('owner_required', 'Доступен только владельцу.', 403)

    async def list_failed(self, principal, *, offset=0):
        self._owner(principal)
        integer(offset, 'offset', maximum=1_000_000)
        async with self.db.session() as session:
            total = await session.scalar(select(func.count()).select_from(Outbox).where(Outbox.state == 'failed'))
            rows = (await session.scalars(select(Outbox).where(Outbox.state == 'failed').order_by(Outbox.id.desc()).offset(offset).limit(20))).all()
            items = []
            for row in rows:
                project = await session.get(Project, row.project_id)
                user = await session.get(User, project.user_id) if project else None
                event = await session.get(Event, row.event_id) if row.event_id is not None else None
                reason = _invalid_reason(row, project, user, self.settings, event)
                items.append(_dto(row) | {'can_retry': reason is None, 'retry_blocked_reason': reason})
            return {'items': items, 'total': total, 'offset': offset, 'limit': 20}

    async def retry(self, principal, row_id):
        self._owner(principal)
        async with self.db.session() as session:
            row, project, user, event = await _context(session, row_id)
            if row is None: raise not_found()
            reason = _invalid_reason(row, project, user, self.settings, event)
            if reason or row.state not in ('failed', 'pending', 'delivering', 'sent'):
                raise DomainError('notification_not_retryable', 'Это уведомление больше нельзя повторить.', 409)
            # Repeating the request while queued/in flight/already sent is a no-op.
            if row.state == 'failed':
                row.state, row.attempts, row.error_code = 'pending', 0, None
                row.next_attempt_at = self.clock()
                _release(row)
            return _dto(row)


class OutboxWorker:
    def __init__(self, database, settings, sender, *, clock=utcnow, send_timeout=35):
        if not 0 < send_timeout < LEASE_SECONDS - 10:
            raise ValueError('Send timeout must leave time to finish the delivery lease.')
        self.db, self.settings, self.sender, self.clock = database, settings, sender, clock
        self.worker_id, self.send_timeout = new_id(), send_timeout

    async def claim_events(self, worker_id, lease_seconds=LEASE_SECONDS, *, limit=1):
        if not isinstance(worker_id, str) or not 1 <= len(worker_id) <= 36: raise ValueError('Invalid worker ID')
        if lease_seconds != LEASE_SECONDS: raise ValueError('The delivery lease is 60 seconds')
        integer(limit, 'limit', minimum=1, maximum=100)
        now = self.clock()
        async with self.db.session() as session:
            # Exhaustion after a crash is terminal too; do not strand delivering rows.
            exhausted = (await session.scalars(select(Outbox).where(Outbox.state == 'delivering', Outbox.attempts >= MAX_ATTEMPTS,
                Outbox.lease_until <= now, Outbox.legacy_event_key.is_(None)).with_for_update(skip_locked=True).limit(100))).all()
            for row in exhausted:
                row.state, row.error_code = 'failed', 'delivery_unknown'
                _release(row)
            due = or_((Outbox.state == 'pending') & (Outbox.next_attempt_at <= now),
                      (Outbox.state == 'delivering') & (Outbox.lease_until <= now))
            rows = (await session.scalars(select(Outbox).where(due, Outbox.attempts < MAX_ATTEMPTS,
                Outbox.legacy_event_key.is_(None)).order_by(Outbox.next_attempt_at, Outbox.id).with_for_update(skip_locked=True).limit(limit))).all()
            for row in rows:
                row.state, row.worker_id, row.lease_until = 'delivering', worker_id, now + timedelta(seconds=LEASE_SECONDS)
                row.attempts += 1
            return [row.id for row in rows]

    def _owns(self, row):
        return row is not None and row.state == 'delivering' and row.worker_id == self.worker_id and row.lease_until is not None and as_utc(row.lease_until) > as_utc(self.clock())

    async def _prepare(self, row_id):
        async with self.db.session() as session:
            row, project, user, event = await _context(session, row_id)
            if not self._owns(row): return None
            reason = _invalid_reason(row, project, user, self.settings, event)
            if reason:
                row.state, row.error_code = 'cancelled', reason
                _release(row)
                return None
            route = '/owner/projects/' if row.recipient_role == 'owner' else '/projects/'
            # Resolve at delivery time so changes since enqueueing apply to each recipient.
            recipient = user if row.recipient_id == user.id else await session.get(User, row.recipient_id)
            language = normalize_language(recipient.language_code if recipient else None)
            return Notification(row.id, project.id, row.recipient_id, row.kind,
                self.settings.app_origin + route + str(project.id), language_code=language)

    async def _sent(self, row_id, message_id):
        async with self.db.session() as session:
            row = await session.scalar(select(Outbox).where(Outbox.id == row_id).with_for_update())
            if not self._owns(row): return
            row.state, row.message_id, row.error_code = 'sent', message_id, None
            _release(row)

    async def _failed(self, row_id, failure):
        async with self.db.session() as session:
            row, project, user, event = await _context(session, row_id)
            if not self._owns(row): return
            reason = _invalid_reason(row, project, user, self.settings, event)
            row.error_code = reason or failure.code
            if reason: row.state = 'cancelled'
            elif failure.permanent or row.attempts >= MAX_ATTEMPTS: row.state = 'failed'
            else:
                row.state = 'pending'
                delay = DELAYS[row.attempts - 1]
                if failure.retry_after is not None:
                    delay = max(delay, max(1, int(failure.retry_after)))
                row.next_attempt_at = self.clock() + timedelta(seconds=delay)
            _release(row)

    async def run_once(self, limit=10):
        integer(limit, 'limit', minimum=1, maximum=100)
        processed = 0
        for _ in range(limit):
            claimed = await self.claim_events(self.worker_id)
            if not claimed: break
            row_id = claimed[0]
            processed += 1
            notification = await self._prepare(row_id)
            if notification is None: continue
            try:
                message_id = await asyncio.wait_for(self.sender.send(notification), timeout=self.send_timeout)
            except DeliveryFailure as failure:
                await self._failed(row_id, failure)
            except TimeoutError:
                await self._failed(row_id, DeliveryFailure('timeout'))
            except Exception:
                # No exception payload: Telegram errors may contain URLs/tokens/text.
                logger.warning('Notification send failed id=%s', row_id)
                await self._failed(row_id, DeliveryFailure())
            else:
                await self._sent(row_id, message_id)
        return processed
