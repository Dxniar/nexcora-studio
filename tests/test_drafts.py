import asyncio
import sqlite3
from repo_helpers import RepoCase
from orderbot.models import Conflict, Cooldown, InvalidInput, NotFound
from orderbot.repository import Repository


class DraftTests(RepoCase):
    async def test_persistent_edit_and_validation(self):
        from orderbot.drafts import DraftService
        service = DraftService(self.repo)
        draft = await service.start(123, 'bot')
        for invalid in (None, 'x'*9, 'x'*2001):
            with self.assertRaises(InvalidInput):
                await service.accept(123, draft.id, draft.revision, invalid)
        draft = await service.accept(123, draft.id, draft.revision, 'x'*2000)
        with self.assertRaises(InvalidInput):
            await service.accept(123, draft.id, draft.revision, 'x'*81)
        draft = await service.accept(123, draft.id, draft.revision, 'x'*80)
        draft = await service.skip(123, draft.id, draft.revision)
        with self.assertRaises(InvalidInput):
            await service.accept(123, draft.id, draft.revision, 'a')
        draft = await service.accept(123, draft.id, draft.revision, 'А'*80)
        reopened = Repository(self.path, clock=self.clock)
        self.assertEqual(await reopened.get_draft(123), draft)
        old = draft
        draft = await service.edit(123, draft.id, draft.revision, 'description')
        draft = await service.accept(123, draft.id, draft.revision, 'Новое описание задачи')
        self.assertEqual(draft.step, 'confirm')
        self.assertEqual(draft.budget, 'x'*80)
        self.assertEqual(draft.name, 'А'*80)
        with self.assertRaises(Conflict):
            await service.submit(123, old.id, old.revision, username=None, admin_id=999)

    async def test_submission_replay_after_repository_restart(self):
        draft = await self.completed_draft()
        async def send(repo):
            return await repo.submit_draft(123, draft.id, draft.revision, username=None, admin_id=999)
        first, second = await asyncio.gather(send(self.repo), send(Repository(self.path, clock=self.clock)))
        self.assertEqual(first.order['id'], second.order['id'])
        replay = await send(Repository(self.path, clock=self.clock))
        self.assertFalse(replay.created)
        self.assertIsNone(await self.repo.get_draft(123))
        self.assertEqual(len(self.query('SELECT * FROM orders')), 1)
        self.assertEqual(len(self.query('SELECT * FROM notification_outbox')), 1)
        with self.assertRaises(NotFound):
            await self.repo.submit_draft(456, draft.id, draft.revision, username=None, admin_id=999)

    async def test_cooldown_and_transaction_rollback(self):
        await self.submitted()
        draft = await self.completed_draft()
        self.clock.value = 1029
        with self.assertRaises(Cooldown) as caught:
            await self.repo.submit_draft(123, draft.id, draft.revision, username=None, admin_id=999)
        self.assertEqual(caught.exception.retry_after, 1)
        self.clock.value = 1030
        await self.repo.submit_draft(123, draft.id, draft.revision, username=None, admin_id=999)
        self.execute("CREATE TRIGGER fail_event BEFORE INSERT ON notification_outbox BEGIN SELECT RAISE(ABORT,'blocked'); END")
        draft = await self.completed_draft(456)
        with self.assertRaises(sqlite3.IntegrityError):
            await self.repo.submit_draft(456, draft.id, draft.revision, username=None, admin_id=999)
        self.assertIsNotNone(await self.repo.get_draft(456))
        self.assertEqual(len(self.query('SELECT * FROM orders')), 2)

    async def test_replace_cancel_back_and_no_admin(self):
        from orderbot.drafts import DraftService
        service = DraftService(self.repo)
        draft = await self.completed_draft()
        with self.assertRaises(Conflict): await service.start(123)
        edited = await service.edit(123, draft.id, draft.revision, 'name')
        back = await service.back(123, edited.id, edited.revision)
        self.assertEqual(back.step, 'confirm')
        self.assertEqual(back.name, 'Айша')
        replacement = await service.start(123, replace=(back.id, back.revision))
        self.assertNotEqual(replacement.id, draft.id)
        self.assertTrue(await self.repo.discard_draft(123, replacement.id, replacement.revision))
        draft = await self.completed_draft()
        await service.submit(123, draft.id, draft.revision, username=None, admin_id=None)
        self.assertEqual(self.query('SELECT * FROM notification_outbox'), [])
