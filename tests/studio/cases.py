"""Isolated application database fixtures; no production login bypass."""
import os
import tempfile
import unittest
from pathlib import Path
from nexcora_studio.db import Database
from nexcora_studio.settings import Settings
from nexcora_studio.models import User
from nexcora_studio.auth import Principal
from tests.studio.helpers import BOT_TOKEN


class StudioCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.url = await self.target_url()
        self.db = Database(self.url)
        await self.db.create_schema()
        self.settings = Settings(bot_token=BOT_TOKEN, admin_id=999, database_url=self.url, app_origin='http://127.0.0.1:8000', development=True)
        async with self.db.session() as session:
            session.add_all([User(id=101, first_name='Алия'), User(id=202, first_name='Другой клиент'), User(id=999, first_name='Владелец')])
        self.client = Principal(101, False)
        self.foreign = Principal(202, False)
        self.owner = Principal(999, True)

    async def asyncTearDown(self):
        await self.db.close()
        self.tmp.cleanup()
        if hasattr(self, 'pg'): await self.pg.close()

    async def target_url(self):
        return f'sqlite+aiosqlite:///{Path(self.tmp.name) / "test.db"}'
