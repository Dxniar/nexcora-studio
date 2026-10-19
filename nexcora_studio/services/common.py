import hashlib
import json
import re
from sqlalchemy import select
from ..auth import as_utc
from ..errors import DomainError, conflict, not_found
from ..models import Attachment, AttachmentGroup, Delivery, Event, Idempotency, Outbox, Project, Proposal, User, utcnow

STATUS_LABELS = {'new': 'Получена', 'discussing': 'Обсуждение', 'proposal_sent': 'Ждём согласования', 'agreed': 'Условия согласованы', 'in_progress': 'В работе', 'review': 'На приёмке', 'completed': 'Завершён', 'closed': 'Закрыт'}


def text_value(value, name, minimum=0, maximum=2000, collapse=False):
    if not isinstance(value, str):
        raise DomainError('invalid_input', f'Поле «{name}» должно быть текстом.', 422)
    value = ' '.join(value.split()) if collapse else value.strip()
    if not minimum <= len(value) <= maximum or '\x00' in value:
        raise DomainError('invalid_input', f'Поле «{name}»: от {minimum} до {maximum} символов.', 422)
    return value


def integer(value, name, minimum=0, maximum=10**12):
    if not isinstance(value, int) or isinstance(value, bool) or not minimum <= value <= maximum:
        raise DomainError('invalid_input', f'Некорректное поле «{name}».', 422)
    return value


async def lock_users(session, *ids):
    users = list((await session.scalars(select(User).where(User.id.in_(sorted(set(ids)))).order_by(User.id).with_for_update())).all())
    if len(users) != len(set(ids)):
        raise not_found()
    return {user.id: user for user in users}


async def replay(session, user_id, operation, key, payload):
    if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z0-9_.:-]{1,100}', key):
        raise DomainError('idempotency_key_required', 'Необходим ключ повторяемой операции.', 422)
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    previous = await session.get(Idempotency, (user_id, operation, key))
    if previous and previous.request_hash != digest:
        raise conflict('Этот ключ уже использован для другого запроса.')
    return previous.response if previous else None, digest


def remember(session, actor_id, operation, key, digest, response, *, project_id=None):
    session.add(Idempotency(user_id=actor_id, operation=operation, key=key, request_hash=digest, response=response, project_id=project_id))


class PortalBase:
    def __init__(self, database, settings, *, clock=utcnow):
        self.db, self.settings, self.clock = database, settings, clock

    def _require_owner(self, actor):
        if not actor.is_owner or actor.user_id != self.settings.admin_id:
            raise DomainError('owner_required', 'Доступен только владельцу.', 403)

    async def _event(self, session, project, actor, kind, data, role):
        event = Event(project_id=project.id, actor_id=actor.user_id, kind=kind, data=data, created_at=self.clock())
        session.add(event)
        await session.flush()
        client = await session.get(User, project.user_id)
        enabled = role == 'owner' or client.notifications_enabled
        session.add(Outbox(event_id=event.id, project_id=project.id, kind=kind,
                           recipient_id=self.settings.admin_id if role == 'owner' else project.user_id,
                           recipient_role=role, project_version=project.version,
                           state='pending' if enabled else 'cancelled', next_attempt_at=self.clock()))

    async def _attachments_dto(self, session, group_id):
        group = await session.get(AttachmentGroup, group_id)
        files = (await session.scalars(select(Attachment).where(Attachment.group_id == group_id, Attachment.state.not_in(('deleted', 'rejected'))).order_by(Attachment.created_at))).all()
        return {'version': group.version, 'count': group.charged_count, 'bytes': group.charged_bytes,
                'max_files': 5, 'max_file_bytes': 10_485_760, 'max_total_bytes': 52_428_800,
                'items': [{'id': item.id, 'filename': item.filename, 'size_bytes': item.actual_bytes or item.declared_bytes,
                           'state': item.state, 'error_code': item.error_code} for item in files]}

    async def _draft_dto(self, session, draft):
        return {'id': draft.id, 'version': draft.version, 'fields': draft.fields,
                'updated_at': as_utc(draft.updated_at).isoformat(),
                'attachments': await self._attachments_dto(session, draft.group_id)}

    def _actions(self, project, owner):
        status = project.status
        if owner:
            actions = []
            if status not in ('closed', 'completed'):
                actions = ['publish_proposal', 'update', 'close']
                if status == 'new': actions.append('discuss')
                if status == 'agreed' and project.accepted_proposal_version == project.proposal_version: actions.append('start')
                if status == 'in_progress' and project.accepted_proposal_version == project.proposal_version and project.proposal_version: actions.append('deliver')
            return actions
        if status == 'proposal_sent': return ['accept_proposal', 'request_changes']
        if status == 'review': return ['accept_delivery', 'request_revision']
        return []

    async def _project_dto(self, session, project, *, owner=False, detail=True):
        next_step = {'new': 'Владелец изучит задачу и ответит', 'discussing': 'Обсудите детали с исполнителем',
                     'proposal_sent': 'Проверьте и согласуйте предложение', 'agreed': 'Ждём начала работы',
                     'in_progress': 'Исполнитель работает над проектом', 'review': 'Проверьте переданный результат',
                     'completed': 'Результат принят', 'closed': 'Обращение закрыто'}
        result = {key: getattr(project, key) for key in ('id', 'service_id', 'service_title', 'name', 'description', 'budget', 'deadline', 'workflow', 'status', 'version', 'proposal_version', 'accepted_proposal_version', 'delivery_version', 'close_reason')}
        result.update(created_at=as_utc(project.created_at).isoformat(), updated_at=as_utc(project.updated_at).isoformat(),
                      status_label=STATUS_LABELS.get(project.status, project.status), next_action=next_step.get(project.status, ''),
                      allowed_actions=self._actions(project, owner))
        if owner:
            user = await session.get(User, project.user_id)
            result['client'] = {'id': project.user_id, 'username': user.username, 'phone': project.phone}
        if detail:
            proposals = (await session.scalars(select(Proposal).where(Proposal.project_id == project.id).order_by(Proposal.version))).all()
            result['proposals'] = [{'version': proposal.version, **proposal.terms, 'created_at': as_utc(proposal.created_at).isoformat()} for proposal in proposals]
            result['proposal'] = next((item for item in result['proposals'] if item['version'] == project.proposal_version), None)
            result['accepted_proposal'] = next((item for item in result['proposals'] if item['version'] == project.accepted_proposal_version), None)
            delivery = await session.scalar(select(Delivery).where(Delivery.project_id == project.id, Delivery.version == project.delivery_version))
            result['delivery'] = {'version': delivery.version, 'description': delivery.description, 'url': delivery.url, 'created_at': as_utc(delivery.created_at).isoformat()} if delivery else None
            events = list((await session.scalars(select(Event).where(Event.project_id == project.id).order_by(Event.id.desc()).limit(201))).all())
            result['has_older_history'] = len(events) > 200
            result['history'] = [{'id': event.id, 'kind': event.kind, 'actor': 'client' if event.actor_id == project.user_id else 'owner', 'created_at': as_utc(event.created_at).isoformat(), 'data': event.data} for event in reversed(events[:200])]
            result['attachments'] = await self._attachments_dto(session, project.group_id)
        return result
