"""Transactional quotas with no SQL transaction held across object I/O."""
import asyncio
from contextlib import suppress
from datetime import timedelta
import hashlib
from pathlib import Path
import tempfile
import unicodedata
from sqlalchemy import select
from ..auth import as_utc
from ..errors import DomainError, conflict, not_found
from ..file_validation import validate_file
from ..models import Attachment, AttachmentGroup, Draft, FileCleanupJob, new_id, utcnow
from .common import PortalBase, integer, lock_users, replay, remember

MAX_FILE = 10_485_760
EXTENSIONS = {'.txt', '.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.webp'}


def display_name(value):
    if not isinstance(value, str) or not value or len(value) > 1024:
        raise DomainError('invalid_filename', 'Укажите имя файла.', 422)
    value = unicodedata.normalize('NFKC', value).replace('\\', '/').split('/')[-1]
    value = ''.join(char for char in value if unicodedata.category(char) not in ('Cc', 'Cf')).strip()
    if not value or len(value) > 180:
        raise DomainError('invalid_filename', 'Имя файла слишком длинное.', 422)
    if Path(value).suffix.lower() not in EXTENSIONS:
        raise DomainError('unsupported_file', 'Принимаются TXT, PDF, DOC/DOCX, JPG, PNG и WebP.', 415)
    return value


class AttachmentService(PortalBase):
    def __init__(self, database, settings, storage, *, clock=utcnow):
        super().__init__(database, settings, clock=clock)
        self.storage = storage
        self.upload_gate = asyncio.Semaphore(2)

    def _require_storage(self):
        if self.storage is None: raise DomainError('storage_unavailable', 'Загрузка временно недоступна.', 503)

    async def _lock_file(self, session, actor, file_id):
        users = await lock_users(session, actor.user_id)
        group_id = await session.scalar(select(Attachment.group_id).join(AttachmentGroup).where(Attachment.id == file_id, AttachmentGroup.user_id == actor.user_id))
        if group_id is None: raise not_found()
        group = await session.scalar(select(AttachmentGroup).where(AttachmentGroup.id == group_id).with_for_update())
        file = await session.scalar(select(Attachment).where(Attachment.id == file_id).with_for_update())
        if group is None or file is None: raise not_found()
        return users[actor.user_id], group, file

    async def reserve(self, actor, filename, size_bytes, expected_attachments_version, key):
        self._require_storage()
        filename = display_name(filename)
        if isinstance(size_bytes, int) and size_bytes > MAX_FILE:
            raise DomainError('file_too_large', 'Размер файла превышает 10 МиБ.', 413)
        size_bytes = integer(size_bytes, 'Размер файла', 1, MAX_FILE)
        async with self.db.session() as session:
            users = await lock_users(session, actor.user_id)
            draft = await session.scalar(select(Draft).where(Draft.user_id == actor.user_id))
            if draft is None: raise not_found()
            operation = 'reserve:' + draft.id
            payload = {'filename': filename, 'size_bytes': size_bytes, 'version': expected_attachments_version}
            previous, digest = await replay(session, actor.user_id, operation, key, payload)
            if previous is not None: return previous
            group = await session.scalar(select(AttachmentGroup).where(AttachmentGroup.id == draft.group_id).with_for_update())
            if group.phase != 'draft' or group.version != integer(expected_attachments_version, 'attachments_version'): raise conflict()
            if group.charged_count >= 5 or group.charged_bytes + size_bytes > 52_428_800:
                raise DomainError('file_quota_exceeded', 'Можно приложить до 5 файлов общим размером до 50 МиБ.', 409)
            file = Attachment(id=new_id(), group_id=group.id, filename=filename, extension=Path(filename).suffix.lower(),
                              declared_bytes=size_bytes, object_key='briefs/' + new_id() + '/' + new_id(),
                              lease_until=self.clock() + timedelta(minutes=15), state='reserved')
            session.add(file)
            await session.flush()
            session.add(FileCleanupJob(object_key=file.object_key, attachment_id=file.id, not_before=file.lease_until + timedelta(seconds=60)))
            group.charged_count += 1
            group.charged_bytes += size_bytes
            group.version += 1
            users[actor.user_id].data_version += 1
            result = {'id': file.id, 'state': file.state, 'filename': file.filename, 'size_bytes': size_bytes, 'expires_at': as_utc(file.lease_until).isoformat(), 'attachments_version': group.version}
            remember(session, actor.user_id, operation, key, digest, result)
            return result

    async def delete(self, actor, file_id):
        async with self.db.session() as session:
            user, group, file = await self._lock_file(session, actor, file_id)
            if group.phase != 'draft': raise conflict('После отправки набор файлов зафиксирован.')
            if file.state == 'deleted': return {'deleted': True}
            if file.state == 'delete_pending': return {'deleted': False, 'state': 'delete_pending'}
            active_writer = file.state in ('uploading', 'validating')
            not_before = as_utc(file.lease_until) + timedelta(seconds=60) if active_writer else self.clock()
            file.state = 'delete_pending'
            if not active_writer: file.lease_until = self.clock()
            job = await session.get(FileCleanupJob, file.object_key)
            if job: job.not_before = not_before
            else: session.add(FileCleanupJob(object_key=file.object_key, attachment_id=file.id, not_before=not_before))
            group.version += 1
            user.data_version += 1
            return {'deleted': False, 'state': 'delete_pending'}

    async def _failed(self, actor, file_id, attempt, code):
        with suppress(Exception):
            async with self.db.session() as session:
                user, group, file = await self._lock_file(session, actor, file_id)
                if file.attempt_id != attempt or file.state in ('ready', 'deleted'): return
                file.state, file.error_code = 'delete_pending', code
                group.version += 1
                user.data_version += 1

    async def _writer_finished(self, object_key):
        # This row survives account erasure. Only a successful PUT response proves
        # the remote writer settled; failures retain a retryable quarantine key.
        async with self.db.session() as session:
            job = await session.scalar(select(FileCleanupJob).where(FileCleanupJob.object_key == object_key).with_for_update())
            if job is not None:
                job.writer_pending = False
                job.not_before = self.clock()

    async def upload(self, actor, file_id, stream, *, content_length=None):
        self._require_storage()
        async with self.upload_gate:
            async with self.db.session() as session:
                user, group, file = await self._lock_file(session, actor, file_id)
                if group.phase != 'draft' or file.state != 'reserved' or as_utc(file.lease_until) <= as_utc(self.clock()): raise conflict('Загрузка уже начата или резерв истёк.')
                if content_length is not None:
                    try:
                        parsed_length = int(content_length)
                    except (ValueError, TypeError):
                        raise DomainError('invalid_size', 'Некорректный размер передачи.', 422) from None
                    if parsed_length != file.declared_bytes:
                        raise DomainError('invalid_size', 'Размер передачи не совпадает с заявленным.', 422)
                file.state = 'uploading'
                file.lease_until = self.clock() + timedelta(seconds=210)
                job = await session.get(FileCleanupJob, file.object_key)
                job.not_before = file.lease_until + timedelta(seconds=60)
                group.version += 1
                user.data_version += 1
                attempt, declared, extension, object_key = file.attempt_id, file.declared_bytes, file.extension, file.object_key
            try:
                with tempfile.TemporaryDirectory(prefix='nexcora-upload-') as folder:
                    path = Path(folder) / 'payload'
                    size, digest = 0, hashlib.sha256()
                    iterator = stream.__aiter__()
                    with path.open('wb') as destination:
                        try:
                            async with asyncio.timeout(120):
                                while True:
                                    try:
                                        async with asyncio.timeout(30): block = await anext(iterator)
                                    except StopAsyncIteration: break
                                    size += len(block)
                                    if size > MAX_FILE or size > declared:
                                        raise DomainError('file_too_large', 'Передано больше байтов, чем разрешено.', 413)
                                    digest.update(block)
                                    destination.write(block)
                        except TimeoutError:
                            raise DomainError('upload_timeout', 'Загрузка заняла слишком много времени.', 408) from None
                    if size != declared:
                        raise DomainError('invalid_size', 'Файл передан не полностью.', 422)
                    async with self.db.session() as session:
                        user, group, file = await self._lock_file(session, actor, file_id)
                        if file.state != 'uploading' or file.attempt_id != attempt or group.phase != 'draft': raise conflict('Загрузка отменена.')
                        file.state = 'validating'
                        group.version += 1
                    detected = await validate_file(path, extension)
                    async with self.db.session() as session:
                        user, group, file = await self._lock_file(session, actor, file_id)
                        if file.state != 'validating' or file.attempt_id != attempt or group.phase != 'draft' or as_utc(file.lease_until) <= as_utc(self.clock()): raise conflict('Загрузка отменена или истекла.')
                        job = await session.scalar(select(FileCleanupJob).where(FileCleanupJob.object_key == object_key).with_for_update())
                        if job is None: raise conflict('Загрузка отменена.')
                        # Persist the key before any write can outlive its lease.
                        job.writer_pending = True
                    await self.storage.put(object_key, path)
                    await self._writer_finished(object_key)
                    async with self.db.session() as session:
                        user, group, file = await self._lock_file(session, actor, file_id)
                        if file.state != 'validating' or file.attempt_id != attempt or group.phase != 'draft' or as_utc(file.lease_until) <= as_utc(self.clock()): raise conflict('Загрузка отменена или истекла.')
                        file.state, file.actual_bytes, file.detected_type, file.sha256 = 'ready', size, detected, digest.hexdigest()
                        file.ready_at, file.lease_until = self.clock(), self.clock()
                        job = await session.get(FileCleanupJob, file.object_key)
                        if job: await session.delete(job)
                        group.version += 1
                        user.data_version += 1
                        await session.flush()
                        return {'id': file.id, 'state': 'ready', 'attachments_version': group.version}
            except BaseException as error:
                await asyncio.shield(self._failed(actor, file_id, attempt, error.code if isinstance(error, DomainError) else 'upload_failed'))
                if isinstance(error, (DomainError, asyncio.CancelledError)): raise
                raise DomainError('storage_unavailable', 'Файл не сохранён. Повторите после завершения очистки.', 503) from None

    async def download(self, actor, file_id, path):
        self._require_storage()
        async with self.db.session() as session:
            row = (await session.execute(select(Attachment, AttachmentGroup).join(AttachmentGroup).where(Attachment.id == file_id))).first()
            if row is None: raise not_found()
            file, group = row
            if file.state != 'ready' or group.phase not in ('draft', 'submitted') or not (group.user_id == actor.user_id or (actor.is_owner and actor.user_id == self.settings.admin_id and group.phase == 'submitted')): raise not_found()
            key, size, sha, name = file.object_key, file.actual_bytes, file.sha256, file.filename
        try:
            await self.storage.get(key, path, MAX_FILE)
            if Path(path).stat().st_size != size:
                raise OSError('object size mismatch')
            with Path(path).open('rb') as body:
                if hashlib.file_digest(body, 'sha256').hexdigest() != sha: raise OSError('object checksum mismatch')
        except Exception:
            raise DomainError('storage_unavailable', 'Не удалось скачать файл. Повторите позже.', 503) from None
        return {'filename': name, 'size_bytes': size}
