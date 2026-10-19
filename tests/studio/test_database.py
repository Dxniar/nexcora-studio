"""Catch missing configuration validation and non-repeatable schema setup."""
import os
import tempfile
import unittest
from pathlib import Path

from nexcora_studio.settings import Settings
from nexcora_studio.db import Database
from nexcora_studio.models import User, Project
from sqlalchemy import select
from nexcora_studio.runtime import loop_factory


class SettingsTests(unittest.TestCase):
    def test_invalid_owner_and_non_https_production_origin_rejected(self):
        base = dict(bot_token='123:synthetic', admin_id=123, database_url='postgresql+psycopg://local/test', app_origin='https://example.test')
        with self.assertRaises(ValueError):
            Settings(**(base | {'admin_id': 0}))
        with self.assertRaises(ValueError):
            Settings(**(base | {'app_origin': 'http://example.test'}))
        with self.assertRaises(ValueError):
            Settings(**(base | {'database_url': 'sqlite+aiosqlite:///local.db'}))

    def test_secret_values_not_present_in_repr(self):
        settings = Settings(bot_token='123:synthetic-secret', admin_id=123, database_url='postgresql+psycopg://name:secret@local/db', app_origin='https://example.test')
        self.assertNotIn('synthetic-secret', repr(settings))
        self.assertNotIn('name:secret', repr(settings))


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(f'sqlite+aiosqlite:///{Path(self.tmp.name) / "test.db"}')

    async def asyncTearDown(self):
        await self.db.close()
        self.tmp.cleanup()

    async def test_schema_twice_preserves_record_and_rollback_is_atomic(self):
        await self.db.create_schema()
        async with self.db.session() as session:
            session.add(User(id=45, first_name='Client'))
        await self.db.create_schema()
        try:
            async with self.db.session() as session:
                session.add(User(id=46, first_name='Rolled back'))
                raise RuntimeError('abort')
        except RuntimeError:
            pass
        async with self.db.session() as session:
            self.assertEqual([45], list((await session.scalars(select(User.id))).all()))


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Dedicated PostgreSQL TEST_DATABASE_URL required')
class PostgresTests(unittest.IsolatedAsyncioTestCase):
    loop_factory = staticmethod(loop_factory)

    async def test_live_postgres_roundtrip_and_schema(self):
        database = Database(os.environ['TEST_DATABASE_URL'])
        self.assertEqual(database.engine.dialect.name, 'postgresql')
        try:
            await database.create_schema()
            async with database.session() as session:
                value = await session.scalar(__import__('sqlalchemy').text('SELECT 41 + 1'))
                self.assertEqual(value, 42)
        finally:
            await database.close()
