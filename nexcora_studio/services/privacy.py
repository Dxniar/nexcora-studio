"""Data access is revoked before asynchronous physical object cleanup."""
from datetime import timedelta
import secrets
from sqlalchemy import delete, select, update
from ..auth import as_utc, token_hash, user_dto
from ..errors import DomainError, conflict
from ..models import Attachment, AttachmentGroup, DeletionConfirmation, FileCleanupJob, Outbox, User
from .common import PortalBase, integer, lock_users


class PrivacyService(PortalBase):
    async def set_language(self, principal, language_code):
        if not isinstance(language_code, str) or language_code not in ('ru', 'en', 'kk'):
            raise DomainError('invalid_input', 'Выберите русский, английский или казахский язык.', 422)
        async with self.db.session() as session:
            users = await lock_users(session, principal.user_id)
            user = users[principal.user_id]
            if user.language_code != language_code:
                user.language_code = language_code
                user.preference_version += 1
                user.data_version += 1
            return user_dto(user, self.settings.admin_id)

    async def set_preferences(self, principal, enabled, expected_version):
        if not isinstance(enabled, bool):
            raise DomainError('invalid_input', 'Укажите настройку уведомлений.', 422)
        async with self.db.session() as session:
            users = await lock_users(session, principal.user_id)
            user = users[principal.user_id]
            if user.preference_version != integer(expected_version, 'version'): raise conflict()
            user.notifications_enabled = enabled
            user.preference_version += 1
            user.data_version += 1
            if not enabled:
                await session.execute(update(Outbox).where(Outbox.recipient_id == user.id, Outbox.recipient_role == 'client', Outbox.state.in_(('pending', 'delivering', 'failed'))).values(state='cancelled', worker_id=None, lease_until=None))
            return user_dto(user, self.settings.admin_id)

    async def confirm_deletion(self, principal):
        token = secrets.token_urlsafe(32)
        expires = self.clock() + timedelta(seconds=300)
        async with self.db.session() as session:
            users = await lock_users(session, principal.user_id)
            await session.execute(delete(DeletionConfirmation).where(DeletionConfirmation.user_id == principal.user_id))
            session.add(DeletionConfirmation(token_hash=token_hash(token), user_id=principal.user_id,
                                              data_version=users[principal.user_id].data_version, expires_at=expires))
        return {'confirmation_token': token, 'expires_at': as_utc(expires).isoformat()}

    async def delete_data(self, principal, confirmation_token):
        if not isinstance(confirmation_token, str) or not 20 <= len(confirmation_token) <= 128:
            raise DomainError('invalid_confirmation', 'Запросите новое подтверждение удаления.', 409)
        async with self.db.session() as session:
            users = await lock_users(session, principal.user_id)
            confirmation = await session.get(DeletionConfirmation, token_hash(confirmation_token))
            if confirmation is None or confirmation.user_id != principal.user_id or confirmation.data_version != users[principal.user_id].data_version or as_utc(confirmation.expires_at) <= as_utc(self.clock()):
                raise DomainError('invalid_confirmation', 'Запросите новое подтверждение удаления.', 409)
            files = list((await session.scalars(select(Attachment).join(AttachmentGroup).where(AttachmentGroup.user_id == principal.user_id).with_for_update())).all())
            for file in files:
                not_before = max(as_utc(self.clock()), as_utc(file.lease_until)) + timedelta(seconds=60)
                job = await session.get(FileCleanupJob, file.object_key)
                if job:
                    job.not_before = max(as_utc(job.not_before), not_before)
                else:
                    session.add(FileCleanupJob(object_key=file.object_key, attachment_id=file.id, not_before=not_before))
            await session.flush()
            # Cascades remove projects/history/sessions and idempotency response copies,
            # including copies made by the owner's account for this client's projects.
            # Cleanup rows retain only opaque keys via ON DELETE SET NULL.
            await session.execute(delete(User).where(User.id == principal.user_id))
        return {'deleted': True, 'physical_cleanup_pending': bool(files)}
