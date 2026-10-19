"""Restore a synthetic PG dump and verify its private blob references.

Requires matching native pg_dump/pg_restore; never accesses the live SQLite or Bucket.
"""
from contextlib import suppress
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from uuid import uuid4
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from nexcora_studio.db import Database
from nexcora_studio.models import Attachment, AttachmentGroup, Project, User
from nexcora_studio.runtime import blocking, loop_factory
from tests.studio.pg_sandbox import PgSandbox


def native_tools():
    folder = os.environ.get('PG_BIN')
    if folder: return Path(folder)
    found = shutil.which('pg_dump')
    return Path(found).parent if found else None


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL') and native_tools(), 'Dedicated PostgreSQL and matching PG_BIN backup tools required')
class RestoreTests(unittest.IsolatedAsyncioTestCase):
    loop_factory = staticmethod(loop_factory)

    async def test_dump_restore_retains_project_and_blob_checksum_references(self):
        import hashlib
        sandbox = PgSandbox()
        source_url = await sandbox.start()
        source = Database(source_url)
        restored_name = 'nexcora_restore_' + uuid4().hex + '_test'
        restored = None
        created = False
        payload = b'Synthetic private brief for restore proof'
        object_key = 'briefs/synthetic-restore/object'
        frozen_blob_copy = {object_key: payload}
        root = make_url(os.environ['TEST_DATABASE_URL'])
        environment = dict(os.environ)
        for key, value in {'PGHOST': root.host or 'localhost', 'PGPORT': str(root.port or 5432), 'PGUSER': root.username or '', 'PGPASSWORD': root.password or ''}.items():
            environment[key] = value
        def run_tool(name, *arguments):
            tool = native_tools() / (name + '.exe' if os.name == 'nt' else name)
            result = subprocess.run([str(tool), *arguments], env=environment, capture_output=True, timeout=30,
                                    creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            if result.returncode:
                raise AssertionError(f'{name} failed in isolated restore test (exit {result.returncode})')
        try:
            await source.create_schema()
            async with source.session() as session:
                session.add(User(id=101, first_name='Synthetic client'))
                await session.flush()
                group = AttachmentGroup(id='restore-group', user_id=101, phase='submitted', charged_count=1, charged_bytes=len(payload))
                session.add(group)
                await session.flush()
                session.add(Project(id=41, user_id=101, group_id=group.id, service_id='bot', service_title='Telegram-бот', name='Synthetic client', description='Synthetic project for restore'))
                from nexcora_studio.models import utcnow
                session.add(Attachment(id='restore-file', group_id=group.id, filename='brief.txt', extension='.txt', declared_bytes=len(payload), actual_bytes=len(payload), detected_type='text/plain', sha256=hashlib.sha256(payload).hexdigest(), state='ready', object_key=object_key, lease_until=utcnow()))
            with tempfile.TemporaryDirectory(prefix='nexcora-restore-proof-') as folder:
                dump = Path(folder) / 'metadata.dump'
                await blocking(run_tool, 'pg_dump', '--dbname', root.database, '--schema', sandbox.schema, '--format=custom', '--file', str(dump))
                self.assertGreater(dump.stat().st_size, 0)
                async with sandbox.admin.engine.connect() as connection:
                    connection = await connection.execution_options(isolation_level='AUTOCOMMIT')
                    await connection.execute(text(f'CREATE DATABASE "{restored_name}"'))
                created = True
                await blocking(run_tool, 'pg_restore', '--exit-on-error', '--dbname', restored_name, str(dump))
                destination = make_url(source_url).set(database=restored_name)
                restored = Database(destination.render_as_string(hide_password=False))
                async with restored.session() as session:
                    project = await session.get(Project, 41)
                    self.assertEqual(project.description, 'Synthetic project for restore')
                    file = await session.get(Attachment, 'restore-file')
                    self.assertEqual(file.actual_bytes, len(frozen_blob_copy[file.object_key]))
                    self.assertEqual(file.sha256, hashlib.sha256(frozen_blob_copy[file.object_key]).hexdigest())
        finally:
            if restored: await restored.close()
            await source.close()
            if created:
                if not re.fullmatch(r'nexcora_restore_[0-9a-f]{32}_test', restored_name): raise ValueError('Invalid disposable database')
                async with sandbox.admin.engine.connect() as connection:
                    connection = await connection.execution_options(isolation_level='AUTOCOMMIT')
                    await connection.execute(text(f'DROP DATABASE "{restored_name}"'))
            await sandbox.close()
