from datetime import date
from urllib.parse import urlsplit
from sqlalchemy import select
from ..errors import DomainError, conflict, not_found
from ..models import Delivery, Project, Proposal
from .common import integer, lock_users, replay, remember, text_value

OWNER_ACTIONS = {'discuss', 'publish_proposal', 'start', 'update', 'deliver', 'close'}
CLIENT_ACTIONS = {'accept_proposal', 'request_changes', 'accept_delivery', 'request_revision'}


def proposal_terms(data, today):
    currency = data.get('currency')
    if currency not in ('KZT', 'USD', 'EUR', 'RUB'):
        raise DomainError('invalid_currency', 'Выберите валюту из списка.', 422)
    try:
        deadline = date.fromisoformat(data.get('deadline', ''))
    except (ValueError, TypeError):
        raise DomainError('invalid_deadline', 'Укажите дату завершения.', 422) from None
    if deadline < today:
        raise DomainError('invalid_deadline', 'Срок не может быть в прошлом.', 422)
    return {'scope': text_value(data.get('scope'), 'Объём работ', 10, 3000),
            'result': text_value(data.get('result'), 'Результат', 10, 2000),
            'price_minor': integer(data.get('price_minor'), 'Цена', minimum=1), 'currency': currency,
            'deadline': deadline.isoformat(), 'revision_terms': text_value(data.get('revision_terms'), 'Правки', 2, 1000)}


class WorkflowOperations:
    async def act(self, principal, project_id, action, data, key, *, owner=False):
        integer(project_id, 'project_id', minimum=1, maximum=2**63 - 1)
        if owner:
            self._require_owner(principal)
        if action not in (OWNER_ACTIONS if owner else CLIENT_ACTIONS):
            raise DomainError('action_forbidden', 'Действие недоступно.', 403)
        async with self.db.session() as session:
            project_user = await session.scalar(select(Project.user_id).where(Project.id == project_id))
            if project_user is None or (not owner and project_user != principal.user_id): raise not_found()
            users = await lock_users(session, project_user, principal.user_id)
            project = await session.scalar(select(Project).where(Project.id == project_id).with_for_update())
            if project is None: raise not_found()
            operation = f'{action}:{project_id}'
            previous, digest = await replay(session, principal.user_id, operation, key, data)
            if previous is not None: return previous
            if project.version != integer(data.get('expected_version'), 'version'): raise conflict()
            if action not in self._actions(project, owner):
                raise DomainError('invalid_transition', 'Действие недоступно на текущем этапе.', 409)
            event_data = {}
            if action == 'discuss':
                project.status = 'discussing'
            elif action == 'publish_proposal':
                terms = proposal_terms(data, self.clock().date())
                project.proposal_version += 1
                session.add(Proposal(project_id=project.id, version=project.proposal_version, terms=terms, created_at=self.clock()))
                project.status = 'proposal_sent'
                event_data = {'proposal_version': project.proposal_version}
            elif action in ('accept_proposal', 'request_changes'):
                version = integer(data.get('proposal_version'), 'proposal_version', minimum=1)
                if version != project.proposal_version: raise conflict('Предложение обновилось. Проверьте актуальную версию.')
                event_data = {'proposal_version': version}
                if action == 'accept_proposal':
                    project.accepted_proposal_version = version
                    project.status = 'agreed'
                else:
                    event_data['comment'] = text_value(data.get('comment'), 'Комментарий', 2, 2000)
                    project.status = 'discussing'
            elif action == 'start':
                project.status = 'in_progress'
            elif action == 'update':
                event_data = {'comment': text_value(data.get('comment'), 'Обновление', 2, 2000)}
            elif action == 'deliver':
                description = text_value(data.get('description'), 'Результат', 10, 2000)
                url = text_value(data.get('url'), 'Ссылка', 1, 2000)
                parsed = urlsplit(url)
                if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or any(char.isspace() for char in url):
                    raise DomainError('invalid_url', 'Укажите HTTPS-ссылку без логина и пароля.', 422)
                project.delivery_version += 1
                session.add(Delivery(project_id=project.id, version=project.delivery_version, description=description, url=url, created_at=self.clock()))
                project.status = 'review'
                event_data = {'delivery_version': project.delivery_version}
            elif action in ('accept_delivery', 'request_revision'):
                version = integer(data.get('delivery_version'), 'delivery_version', minimum=1)
                if version != project.delivery_version: raise conflict('Передана новая версия результата.')
                event_data = {'delivery_version': version}
                if action == 'accept_delivery': project.status = 'completed'
                else:
                    event_data['comment'] = text_value(data.get('comment'), 'Правки', 2, 2000)
                    project.status = 'in_progress'
            elif action == 'close':
                project.close_reason = text_value(data.get('reason'), 'Причина закрытия', 3, 1000)
                project.status = 'closed'
                event_data = {'reason': project.close_reason}
            project.version += 1
            project.updated_at = self.clock()
            users[project.user_id].data_version += 1
            await session.flush()
            await self._event(session, project, principal, action, event_data, 'client' if owner else 'owner')
            await session.flush()
            result = await self._project_dto(session, project, owner=owner)
            remember(session, principal.user_id, operation, key, digest, result, project_id=project.id)
            return result
