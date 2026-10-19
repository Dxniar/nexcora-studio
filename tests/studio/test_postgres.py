"""Business and race checks on the actual PostgreSQL engine."""
import asyncio
import os
import unittest
from sqlalchemy import func, select
from nexcora_studio.errors import DomainError
from nexcora_studio.models import Event, Project
from nexcora_studio.runtime import loop_factory
from tests.studio import test_projects, test_workflow, test_privacy, test_attachments, test_import
from tests.studio.pg_sandbox import PgSandbox


class PostgresMixin:
    loop_factory = staticmethod(loop_factory)

    async def target_url(self):
        self.pg = PgSandbox()
        return await self.pg.start()


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Dedicated PostgreSQL TEST_DATABASE_URL required')
class PostgresProjectTests(PostgresMixin, test_projects.ProjectTests):
    async def test_concurrent_submit_creates_one_project_and_event(self):
        draft = await self.complete_draft()
        async def submit(key):
            return await self.service.submit(self.client, draft['id'], draft['version'], 0, key)
        results = await asyncio.gather(submit('concurrent-one'), submit('concurrent-two'))
        self.assertEqual(results[0]['id'], results[1]['id'])
        async with self.db.session() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(Project)), 1)
            self.assertEqual(await session.scalar(select(func.count()).select_from(Event)), 1)


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Dedicated PostgreSQL TEST_DATABASE_URL required')
class PostgresWorkflowTests(PostgresMixin, test_workflow.WorkflowTests):
    async def test_concurrent_accept_only_one_transition(self):
        project = await self.action(self.owner, 'publish_proposal', **self.terms)
        data = {'expected_version': project['version'], 'proposal_version': 1}
        results = await asyncio.gather(self.service.act(self.client, project['id'], 'accept_proposal', data, 'accept-a'), self.service.act(self.client, project['id'], 'accept_proposal', data, 'accept-b'), return_exceptions=True)
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual(sum(isinstance(result, DomainError) and result.status == 409 for result in results), 1)


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Dedicated PostgreSQL TEST_DATABASE_URL required')
class PostgresPrivacyTests(PostgresMixin, test_privacy.PrivacyTests):
    pass


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Dedicated PostgreSQL TEST_DATABASE_URL required')
class PostgresAttachmentTests(PostgresMixin, test_attachments.AttachmentTests):
    async def test_cleanup_waiting_for_user_lock_preserves_new_reservation_quota(self):
        from unittest.mock import patch
        from nexcora_studio.cleanup import CleanupWorker
        from nexcora_studio.models import AttachmentGroup, utcnow
        from nexcora_studio.services.common import lock_users
        from datetime import timedelta

        file = await self.reserve()
        await self.files.delete(self.client, file['id'])
        loaded, resume = asyncio.Event(), asyncio.Event()
        calls = 0

        async def pause_before_user_lock(session, *user_ids):
            nonlocal calls
            calls += 1
            if calls == 2:
                loaded.set()
                await resume.wait()
            return await lock_users(session, *user_ids)

        worker = CleanupWorker(self.db, self.storage, clock=lambda: utcnow() + timedelta(hours=1))
        with patch('nexcora_studio.cleanup.lock_users', pause_before_user_lock):
            cleanup = asyncio.create_task(worker.run_once(limit=1))
            try:
                await asyncio.wait_for(loaded.wait(), timeout=10)
                await self.reserve()
            finally:
                resume.set()
                await cleanup
        async with self.db.session() as session:
            group = await session.scalar(select(AttachmentGroup).where(AttachmentGroup.user_id == self.client.user_id))
            self.assertEqual((group.charged_count, group.charged_bytes, group.version), (1, 10, 4))

    async def test_concurrent_last_file_slot(self):
        for _ in range(4): await self.reserve()
        draft = await self.portal.get_draft(self.client)
        version = draft['attachments']['version']
        results = await asyncio.gather(self.files.reserve(self.client, 'one.txt', 10, version, 'slot-a'), self.files.reserve(self.client, 'two.txt', 10, version, 'slot-b'), return_exceptions=True)
        self.assertEqual(sum(isinstance(result, dict) for result in results), 1)
        self.assertEqual((await self.portal.get_draft(self.client))['attachments']['count'], 5)


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Dedicated PostgreSQL TEST_DATABASE_URL required')
class PostgresImportTests(PostgresMixin, test_import.ImportTests):
    async def test_sequence_after_import_advances_past_preserved_id(self):
        from nexcora_studio.legacy_import import import_legacy
        from nexcora_studio.models import AttachmentGroup, new_id
        await import_legacy(self.source, self.url, dry_run=False)
        async with self.db.session() as session:
            group = AttachmentGroup(id=new_id(), user_id=112233445566, phase='submitted')
            session.add(group)
            await session.flush()
            project = Project(user_id=112233445566, group_id=group.id, service_title='Новая задача', service_id='other', name='Клиент', description='Новая задача после переноса')
            session.add(project)
            await session.flush()
            self.assertEqual(project.id, 9002)
