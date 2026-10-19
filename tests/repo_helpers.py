from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from orderbot.repository import Repository


class Clock:
    value = 1000.0
    def __call__(self): return self.value


class RepoCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'orders.sqlite3'
        self.clock = Clock()
        self.repo = Repository(self.path, clock=self.clock)
        await self.repo.initialize()

    def query(self, sql, args=()):
        with closing(sqlite3.connect(self.path)) as db:
            db.row_factory = sqlite3.Row
            return [dict(r) for r in db.execute(sql, args)]

    def execute(self, sql):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute(sql)
            db.commit()

    async def completed_draft(self, user_id=123):
        from orderbot.drafts import DraftService
        service = DraftService(self.repo)
        draft = await service.start(user_id, 'bot')
        for value in ('Описание задачи клиента', '', '', 'Айша'):
            if value:
                draft = await service.accept(user_id, draft.id, draft.revision, value)
            else:
                draft = await service.skip(user_id, draft.id, draft.revision)
        return draft

    async def submitted(self, user_id=123):
        draft = await self.completed_draft(user_id)
        return await self.repo.submit_draft(user_id, draft.id, draft.revision,
                                          username='client_user', admin_id=999)
