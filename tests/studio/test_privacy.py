from datetime import timedelta
from sqlalchemy import func, select
from nexcora_studio.errors import DomainError
from nexcora_studio.models import Idempotency, Project, Session, User, DeletionConfirmation
from nexcora_studio.models import utcnow
from nexcora_studio.services.privacy import PrivacyService
from nexcora_studio.services.projects import ProjectService
from tests.studio.cases import StudioCase


class PrivacyTests(StudioCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.privacy = PrivacyService(self.db, self.settings)

    async def test_preference_conflict_and_confirmation_invalidated_by_change(self):
        confirmation = await self.privacy.confirm_deletion(self.client)
        async with self.db.session() as session:
            stored = (await session.scalars(select(DeletionConfirmation))).one()
            self.assertNotEqual(stored.token_hash, confirmation['confirmation_token'])
        await self.privacy.set_preferences(self.client, False, 0)
        with self.assertRaises(DomainError) as caught:
            await self.privacy.set_preferences(self.client, True, 0)
        self.assertEqual(caught.exception.status, 409)
        with self.assertRaises(DomainError):
            await self.privacy.delete_data(self.client, confirmation['confirmation_token'])
        async with self.db.session() as session:
            self.assertFalse((await session.get(User, 101)).notifications_enabled)

    async def test_deletion_removes_owner_response_copies_revokes_sessions_and_preserves_foreign(self):
        portal = ProjectService(self.db, self.settings)
        draft = await portal.get_draft(self.client)
        draft = await portal.save_draft(self.client, {'name': 'Алия', 'description': 'Нужен бот для заявок', 'service_id': 'bot'}, 0)
        project = await portal.submit(self.client, draft['id'], draft['version'], 0, 'submit')
        await portal.act(self.owner, project['id'], 'discuss', {'expected_version': 0}, 'owner-response', owner=True)
        async with self.db.session() as session:
            session.add(Session(token_hash='a' * 64, user_id=101, expires_at=utcnow() + timedelta(hours=1)))
        confirmation = await self.privacy.confirm_deletion(self.client)
        with self.assertRaises(DomainError):
            await self.privacy.delete_data(self.foreign, confirmation['confirmation_token'])
        await self.privacy.delete_data(self.client, confirmation['confirmation_token'])
        async with self.db.session() as session:
            self.assertIsNone(await session.get(User, 101))
            self.assertIsNotNone(await session.get(User, 202))
            self.assertEqual(await session.scalar(select(func.count()).select_from(Project)), 0)
            self.assertEqual(await session.scalar(select(func.count()).select_from(Idempotency)), 0)
            self.assertEqual(await session.scalar(select(func.count()).select_from(Session)), 0)

    async def test_expired_confirmation_cannot_erase_data(self):
        now = utcnow()
        self.privacy.clock = lambda: now
        confirmation = await self.privacy.confirm_deletion(self.client)
        self.privacy.clock = lambda: now + timedelta(seconds=301)
        with self.assertRaises(DomainError):
            await self.privacy.delete_data(self.client, confirmation['confirmation_token'])
        async with self.db.session() as session:
            self.assertIsNotNone(await session.get(User, 101))
