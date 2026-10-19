import asyncio
from datetime import timedelta
from pathlib import Path
import tempfile
from sqlalchemy import select
from nexcora_studio.errors import DomainError
from nexcora_studio.models import Attachment, AttachmentGroup, FileCleanupJob
from nexcora_studio.services.attachments import AttachmentService
from nexcora_studio.services.projects import ProjectService
from nexcora_studio.services.privacy import PrivacyService
from nexcora_studio.cleanup import CleanupWorker
from nexcora_studio.models import utcnow
from tests.studio.cases import StudioCase
from tests.studio.fakes import MemoryStorage


async def chunks(data):
    yield data


class DelayedPutStorage(MemoryStorage):
    def __init__(self):
        super().__init__()
        self.entered, self.release = asyncio.Event(), asyncio.Event()
        self.after_put = None

    async def put(self, key, path):
        self.entered.set()
        await self.release.wait()
        await super().put(key, path)
        if self.after_put: self.after_put()


class AttachmentTests(StudioCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.storage = MemoryStorage()
        self.portal = ProjectService(self.db, self.settings)
        self.files = AttachmentService(self.db, self.settings, self.storage)
        self.draft = await self.portal.get_draft(self.client)

    async def reserve(self, data=b'Brief text', version=None):
        draft = await self.portal.get_draft(self.client)
        return await self.files.reserve(self.client, 'brief.txt', len(data), draft['attachments']['version'] if version is None else version, f'file-{draft["attachments"]["version"]}')

    async def start_delayed_put(self):
        self.now = utcnow()
        self.files.clock = lambda: self.now
        self.storage = self.files.storage = DelayedPutStorage()
        file = await self.reserve()
        task = asyncio.create_task(self.files.upload(self.client, file['id'], chunks(b'Brief text'), content_length=10))
        await asyncio.wait_for(self.storage.entered.wait(), timeout=10)
        return file, task

    async def test_expired_writer_keeps_cleanup_key_until_late_put_is_removed(self):
        file, task = await self.start_delayed_put()
        self.now += timedelta(seconds=271)
        worker = CleanupWorker(self.db, self.storage, clock=lambda: self.now)
        try:
            await worker.run_once()
            async with self.db.session() as session:
                record = await session.get(Attachment, file['id'])
                self.assertEqual(record.state, 'delete_pending')
                self.assertEqual((await session.get(AttachmentGroup, record.group_id)).charged_count, 1)
                self.assertIsNotNone(await session.scalar(select(FileCleanupJob)))
        finally:
            self.storage.release.set()
            result, = await asyncio.gather(task, return_exceptions=True)
        self.assertIsInstance(result, DomainError)
        self.now += timedelta(minutes=1)
        await CleanupWorker(self.db, self.storage, clock=lambda: self.now).run_once()
        self.assertEqual(self.storage.objects, {})
        async with self.db.session() as session:
            self.assertIsNone(await session.scalar(select(FileCleanupJob)))
            record = await session.get(Attachment, file['id'])
            self.assertEqual(record.state, 'deleted')
            self.assertEqual((await session.get(AttachmentGroup, record.group_id)).charged_count, 0)

    async def test_erased_account_keeps_cleanup_for_a_writer_finishing_after_deletion(self):
        file, task = await self.start_delayed_put()
        try:
            privacy = PrivacyService(self.db, self.settings, clock=lambda: self.now)
            confirmation = await privacy.confirm_deletion(self.client)
            await privacy.delete_data(self.client, confirmation['confirmation_token'])
            self.now += timedelta(seconds=271)
            await CleanupWorker(self.db, self.storage, clock=lambda: self.now).run_once()
            async with self.db.session() as session:
                self.assertIsNone(await session.get(Attachment, file['id']))
                self.assertIsNotNone(await session.scalar(select(FileCleanupJob)))
        finally:
            self.storage.release.set()
            result, = await asyncio.gather(task, return_exceptions=True)
        self.assertIsInstance(result, DomainError)
        self.now += timedelta(minutes=1)
        await CleanupWorker(self.db, self.storage, clock=lambda: self.now).run_once()
        self.assertEqual(self.storage.objects, {})

    async def test_delete_started_before_writer_settled_requires_another_delete(self):
        _, task = await self.start_delayed_put()
        deleted, finish = asyncio.Event(), asyncio.Event()

        class PausedFinishWorker(CleanupWorker):
            async def _finish(inner, *args, **kwargs):
                deleted.set()
                await finish.wait()
                return await super()._finish(*args, **kwargs)

        self.now += timedelta(seconds=271)
        cleanup = asyncio.create_task(PausedFinishWorker(self.db, self.storage, clock=lambda: self.now).run_once())
        try:
            await asyncio.wait_for(deleted.wait(), timeout=10)
            self.storage.release.set()
            result, = await asyncio.gather(task, return_exceptions=True)
            self.assertIsInstance(result, DomainError)
            self.assertEqual(list(self.storage.objects.values()), [b'Brief text'])
        finally:
            self.storage.release.set()
            finish.set()
            await asyncio.gather(task, cleanup, return_exceptions=True)
        self.now += timedelta(minutes=1)
        await CleanupWorker(self.db, self.storage, clock=lambda: self.now).run_once()
        self.assertEqual(self.storage.objects, {})

    async def test_postwrite_database_outage_keeps_a_restart_safe_cleanup_tombstone(self):
        _, task = await self.start_delayed_put()

        class UnavailableDatabase:
            def session(inner): raise OSError('synthetic metadata outage')

        self.storage.after_put = lambda: setattr(self.files, 'db', UnavailableDatabase())
        self.storage.release.set()
        with self.assertRaises(DomainError): await task
        self.now += timedelta(seconds=271)
        await CleanupWorker(self.db, self.storage, clock=lambda: self.now).run_once()
        self.assertEqual(self.storage.objects, {})
        async with self.db.session() as session:
            job = await session.scalar(select(FileCleanupJob))
            self.assertIsNotNone(job)
            key = job.object_key
        # A crashed request can still be accepted remotely after the first DELETE.
        self.storage.objects[key] = b'Brief text'
        self.now += timedelta(minutes=1)
        await CleanupWorker(self.db, self.storage, clock=lambda: self.now).run_once()
        self.assertEqual(self.storage.objects, {})

    async def test_sixth_file_and_byte_over_limit_rejected(self):
        for _ in range(5): await self.reserve()
        with self.assertRaises(DomainError) as caught: await self.reserve()
        self.assertEqual(caught.exception.status, 409)
        with self.assertRaises(DomainError) as caught:
            await self.files.reserve(self.foreign, 'large.txt', 10_485_761, 0, 'oversize')
        self.assertEqual(caught.exception.status, 413)

    async def test_actual_stream_size_and_foreign_or_owner_draft_access(self):
        file = await self.reserve()
        with self.assertRaises(DomainError):
            await self.files.upload(self.client, file['id'], chunks(b'Brief text' + b'x'), content_length=None)
        file = await self.reserve(b'Another brief')
        await self.files.upload(self.client, file['id'], chunks(b'Another brief'), content_length=None)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'download'
            with self.assertRaises(DomainError) as caught:
                await self.files.download(self.foreign, file['id'], path)
            self.assertEqual(caught.exception.status, 404)
            with self.assertRaises(DomainError): await self.files.download(self.owner, file['id'], path)
            metadata = await self.files.download(self.client, file['id'], path)
            self.assertEqual(path.read_bytes(), b'Another brief')

    async def test_submit_while_reserved_and_cancelled_writer_never_ready(self):
        draft = await self.portal.save_draft(self.client, {'service_id': 'bot', 'name': 'Алия', 'description': 'Бот для обращений'}, 0)
        file = await self.reserve()
        current = await self.portal.get_draft(self.client)
        with self.assertRaises(DomainError) as caught:
            await self.portal.submit(self.client, draft['id'], draft['version'], current['attachments']['version'], 'submit-busy')
        self.assertEqual(caught.exception.code, 'uploads_in_progress')
        await self.files.delete(self.client, file['id'])
        with self.assertRaises(DomainError):
            await self.files.upload(self.client, file['id'], chunks(b'Brief text'), content_length=10)
        async with self.db.session() as session:
            self.assertNotEqual((await session.get(Attachment, file['id'])).state, 'ready')

    async def test_lost_put_response_keeps_durable_cleanup_until_delete_succeeds(self):
        file = await self.reserve()
        self.storage.fail_after_put = True
        with self.assertRaises(DomainError):
            await self.files.upload(self.client, file['id'], chunks(b'Brief text'), content_length=10)
        self.assertEqual(len(self.storage.objects), 1)
        future = self.portal.clock() + timedelta(hours=1)
        worker = CleanupWorker(self.db, self.storage, clock=lambda: future)
        self.storage.fail_delete = True
        await worker.run_once()
        self.assertEqual(len(self.storage.objects), 1)
        async with self.db.session() as session:
            self.assertIsNotNone(await session.scalar(select(FileCleanupJob)))
        self.storage.fail_delete = False
        future += timedelta(seconds=30)
        await worker.run_once()
        self.assertEqual(self.storage.objects, {})

    async def test_repeated_delete_does_not_shorten_active_writer_cleanup_grace(self):
        file = await self.reserve()
        future = utcnow() + timedelta(minutes=3)
        async with self.db.session() as session:
            record = await session.get(Attachment, file['id'])
            record.state, record.lease_until = 'uploading', future
        await self.files.delete(self.client, file['id'])
        await self.files.delete(self.client, file['id'])
        async with self.db.session() as session:
            job = await session.scalar(select(FileCleanupJob))
            from nexcora_studio.auth import as_utc
            self.assertGreater(as_utc(job.not_before), future)
