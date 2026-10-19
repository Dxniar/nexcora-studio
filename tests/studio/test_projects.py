"""Sending a draft is one atomic, replay-safe business operation."""
from sqlalchemy import select, func
from nexcora_studio.errors import DomainError
from nexcora_studio.models import Event, Outbox
from nexcora_studio.services.projects import ProjectService
from tests.studio.cases import StudioCase


class ProjectTests(StudioCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.service = ProjectService(self.db, self.settings)

    async def complete_draft(self):
        draft = await self.service.get_draft(self.client)
        return await self.service.save_draft(self.client, {'service_id': 'bot', 'name': '  Алия  ', 'description': 'Нужен бот для записи на услуги', 'budget': 'Обсудим', 'deadline': ''}, draft['version'])

    async def test_stale_update_is_conflict_and_saved_draft_survives_service_restart(self):
        initial = await self.service.get_draft(self.client)
        saved = await self.complete_draft()
        recreated = ProjectService(self.db, self.settings)
        self.assertEqual((await recreated.get_draft(self.client))['fields']['name'], 'Алия')
        with self.assertRaises(DomainError) as caught:
            await recreated.save_draft(self.client, {'description': 'Old browser'}, initial['version'])
        self.assertEqual(caught.exception.status, 409)

    async def test_submit_replay_before_cooldown_one_event_no_foreign_access(self):
        draft = await self.complete_draft()
        args = (self.client, draft['id'], draft['version'], draft['attachments']['version'], 'submit-test-key')
        project = await self.service.submit(*args)
        replay = await self.service.submit(*args)
        self.assertEqual(project['id'], replay['id'])
        self.assertEqual(project['status'], 'new')
        self.assertEqual(project['service_id'], 'bot')
        async with self.db.session() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(Event)), 1)
            self.assertEqual(await session.scalar(select(func.count()).select_from(Outbox)), 1)
        with self.assertRaises(DomainError) as caught:
            await self.service.get_project(self.foreign, project['id'])
        self.assertEqual(caught.exception.status, 404)
        following = await self.complete_draft()
        with self.assertRaises(DomainError) as caught:
            await self.service.submit(self.client, following['id'], following['version'], 0, 'new-test-key')
        self.assertEqual(caught.exception.status, 429)

    async def test_idempotency_key_reuse_with_changed_payload_rejected(self):
        draft = await self.complete_draft()
        await self.service.submit(self.client, draft['id'], draft['version'], 0, 'same-key')
        with self.assertRaises(DomainError) as caught:
            await self.service.submit(self.client, draft['id'], draft['version'] + 1, 0, 'same-key')
        self.assertEqual(caught.exception.status, 409)
