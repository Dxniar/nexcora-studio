"""Retryable object deletion, including interrupted uploads and erased accounts."""
from datetime import timedelta
from sqlalchemy import or_, select
from .auth import as_utc
from .models import Attachment, AttachmentGroup, FileCleanupJob, new_id, utcnow
from .services.common import lock_users


class CleanupWorker:
    def __init__(self, database, storage, *, clock=utcnow):
        self.db, self.storage, self.clock, self.worker_id = database, storage, clock, new_id()

    async def _claim(self):
        now = self.clock()
        async with self.db.session() as session:
            job = await session.scalar(select(FileCleanupJob).where(FileCleanupJob.not_before <= now,
                or_(FileCleanupJob.lease_until.is_(None), FileCleanupJob.lease_until <= now)).order_by(FileCleanupJob.not_before).with_for_update(skip_locked=True).limit(1))
            if job is None: return None
            job.worker_id, job.lease_until = self.worker_id, now + timedelta(seconds=120)
            return job.object_key, job.attachment_id

    async def _lock_records(self, session, key, attachment_id):
        # Preliminary identity reads must not populate the ORM identity map:
        # another reservation may commit while we wait for the user lock.
        identity = (await session.execute(select(Attachment.group_id, AttachmentGroup.user_id)
            .join(AttachmentGroup, Attachment.group_id == AttachmentGroup.id)
            .where(Attachment.id == attachment_id))).first() if attachment_id else None
        group = file = None
        if identity:
            group_id, user_id = identity
            await lock_users(session, user_id)
            group = await session.scalar(select(AttachmentGroup).where(AttachmentGroup.id == group_id).with_for_update())
            file = await session.scalar(select(Attachment).where(Attachment.id == attachment_id).with_for_update())
        job = await session.scalar(select(FileCleanupJob).where(FileCleanupJob.object_key == key).with_for_update())
        if job is None or job.worker_id != self.worker_id: return None, None, None
        return job, group, file

    async def _prepare(self, key, attachment_id):
        async with self.db.session() as session:
            job, group, file = await self._lock_records(session, key, attachment_id)
            if job is None: return None
            if file and file.state == 'ready':
                await session.delete(job)
                return None
            if file and file.state in ('uploading', 'validating') and as_utc(file.lease_until) + timedelta(seconds=60) > as_utc(self.clock()):
                job.not_before, job.lease_until, job.worker_id = as_utc(file.lease_until) + timedelta(seconds=60), None, None
                return None
            if file and file.state != 'deleted':
                file.state = 'delete_pending'
            return job.writer_pending

    async def _finish(self, key, attachment_id, writer_was_pending):
        async with self.db.session() as session:
            job, group, file = await self._lock_records(session, key, attachment_id)
            if job is None: return
            if file and file.state == 'ready': return  # Never remove a ready record.
            # A PUT may complete after this DELETE. Even if the uploader settled
            # meanwhile, only another DELETE begun after settlement is final.
            if writer_was_pending or job.writer_pending:
                job.not_before = self.clock() + timedelta(seconds=10)
                job.lease_until, job.worker_id = None, None
            else:
                if file and file.state != 'deleted':
                    file.state = 'deleted'
                    if group:
                        group.charged_count -= 1
                        group.charged_bytes -= file.declared_bytes
                        group.version += 1
                await session.delete(job)

    async def _retry(self, key):
        async with self.db.session() as session:
            job = await session.scalar(select(FileCleanupJob).where(FileCleanupJob.object_key == key).with_for_update())
            if job is not None and job.worker_id == self.worker_id:
                job.attempts += 1
                job.not_before = self.clock() + timedelta(seconds=min(3600, 10 * 2 ** min(job.attempts - 1, 8)))
                job.lease_until, job.worker_id = None, None

    async def run_once(self, limit=10):
        count = 0
        for _ in range(limit):
            claimed = await self._claim()
            if claimed is None: break
            key, attachment_id = claimed
            try:
                writer_was_pending = await self._prepare(key, attachment_id)
                if writer_was_pending is not None:
                    await self.storage.delete(key)
                    await self._finish(key, attachment_id, writer_was_pending)
                    count += 1
            except Exception:
                await self._retry(key)
        return count
