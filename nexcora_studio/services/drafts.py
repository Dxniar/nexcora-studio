from datetime import timedelta
from sqlalchemy import select
from orderbot.catalog import get_service
from ..auth import as_utc
from ..errors import DomainError, conflict, not_found
from ..models import Attachment, AttachmentGroup, Draft, Project, new_id
from .common import integer, lock_users, replay, remember, text_value


class DraftOperations:
    async def get_draft(self, principal):
        async with self.db.session() as session:
            users = await lock_users(session, principal.user_id)
            draft = await session.scalar(select(Draft).where(Draft.user_id == principal.user_id))
            if draft is None:
                group = AttachmentGroup(id=new_id(), user_id=principal.user_id, phase='draft')
                session.add(group)
                await session.flush()
                draft = Draft(id=new_id(), user_id=principal.user_id, group_id=group.id, fields={}, updated_at=self.clock())
                session.add(draft)
                users[principal.user_id].data_version += 1
                await session.flush()
            return await self._draft_dto(session, draft)

    async def save_draft(self, principal, fields, expected_version):
        if not isinstance(fields, dict) or set(fields) - {'service_id', 'name', 'description', 'budget', 'deadline'}:
            raise DomainError('invalid_input', 'Некорректные поля черновика.', 422)
        clean = {}
        for name, value in fields.items():
            if name == 'service_id':
                if value not in (None, '') and (not isinstance(value, str) or not get_service(value)):
                    raise DomainError('invalid_service', 'Выберите услугу из каталога.', 422)
                clean[name] = value or None
            else:
                clean[name] = text_value(value, name, maximum=2000 if name == 'description' else 80, collapse=name == 'name')
        expected_version = integer(expected_version, 'version')
        async with self.db.session() as session:
            users = await lock_users(session, principal.user_id)
            draft = await session.scalar(select(Draft).where(Draft.user_id == principal.user_id).with_for_update())
            if draft is None: raise not_found()
            if draft.version != expected_version: raise conflict(details={'current_version': draft.version})
            draft.fields = {**draft.fields, **clean}
            draft.version += 1
            draft.updated_at = self.clock()
            users[principal.user_id].data_version += 1
            await session.flush()
            return await self._draft_dto(session, draft)

    async def submit(self, principal, draft_id, expected_version, attachments_version, key):
        payload = {'draft_id': draft_id, 'expected_version': expected_version, 'attachments_version': attachments_version}
        operation = f'submit:{draft_id}'
        async with self.db.session() as session:
            users = await lock_users(session, principal.user_id)
            previous, digest = await replay(session, principal.user_id, operation, key, payload)
            if previous is not None: return previous
            submitted = await session.scalar(select(Project).where(Project.draft_id == draft_id, Project.user_id == principal.user_id))
            if submitted:
                result = await self._project_dto(session, submitted)
                remember(session, principal.user_id, operation, key, digest, result, project_id=submitted.id)
                return result
            draft = await session.scalar(select(Draft).where(Draft.id == draft_id, Draft.user_id == principal.user_id).with_for_update())
            if not draft: raise not_found()
            if draft.version != integer(expected_version, 'version'): raise conflict()
            group = await session.scalar(select(AttachmentGroup).where(AttachmentGroup.id == draft.group_id).with_for_update())
            if group.phase != 'draft' or group.version != integer(attachments_version, 'attachments_version'): raise conflict()
            busy = await session.scalar(select(Attachment.id).where(Attachment.group_id == group.id, Attachment.state.in_(('reserved', 'uploading', 'validating', 'delete_pending'))).limit(1))
            if busy: raise DomainError('uploads_in_progress', 'Дождитесь завершения загрузки или удаления файлов.', 409)
            fields = draft.fields
            service = get_service(fields.get('service_id'))
            if not service: raise DomainError('invalid_service', 'Выберите услугу.', 422)
            name = text_value(fields.get('name', ''), 'Имя', 2, 80, collapse=True)
            description = text_value(fields.get('description', ''), 'Описание', 10, 2000)
            user = users[principal.user_id]
            if user.last_submission_at and as_utc(self.clock()) - as_utc(user.last_submission_at) < timedelta(seconds=30):
                raise DomainError('submission_cooldown', 'Следующее обращение можно отправить через 30 секунд.', 429)
            project = Project(user_id=user.id, draft_id=draft.id, group_id=group.id, service_id=service.id, service_title=service.title,
                              name=name, description=description, budget=text_value(fields.get('budget', ''), 'Бюджет', maximum=80),
                              deadline=text_value(fields.get('deadline', ''), 'Срок', maximum=80), created_at=self.clock(), updated_at=self.clock())
            session.add(project)
            group.phase = 'submitted'
            group.version += 1
            user.last_submission_at = self.clock()
            user.data_version += 1
            await session.flush()
            await self._event(session, project, principal, 'submitted', {}, 'owner')
            await session.delete(draft)
            await session.flush()
            result = await self._project_dto(session, project)
            remember(session, principal.user_id, operation, key, digest, result, project_id=project.id)
            return result
