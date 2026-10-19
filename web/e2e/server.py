"""Disposable browser fixture: real app/services/auth, temporary DB, local object I/O."""
import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys
import tempfile
import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from nexcora_studio.app import create_app
from nexcora_studio.db import Database
from nexcora_studio.models import AttachmentGroup, Project, User
from nexcora_studio.settings import Settings
from tests.studio.helpers import BOT_TOKEN


class TestStorage:
    def __init__(self, folder): self.folder = Path(folder)
    def path(self, key):
        import hashlib
        return self.folder / hashlib.sha256(key.encode()).hexdigest()
    async def put(self, key, source): self.path(key).write_bytes(Path(source).read_bytes())
    async def get(self, key, target, maximum):
        data = self.path(key).read_bytes()
        if len(data) > maximum: raise ValueError('Fixture object too large')
        Path(target).write_bytes(data)
    async def delete(self, key): self.path(key).unlink(missing_ok=True)


async def seed_workspace_examples(db):
    """Synthetic list states in this temporary database only; never a login bypass.

    92001: one old active project hidden behind twelve newer closed projects.
    92002: history only. 92006: each owner queue stage, including three attention
    stages. Other browser tests keep using their own independent client IDs.
    """
    async with db.session() as session:
        for user_id in (92001, 92002, 92006, 97105):
            session.add(User(id=user_id, first_name='Синтетический клиент', username=f'workspace_{user_id}'))
        await session.flush()

        async def project(project_id, user_id, status, title, created_at, service_id='bot'):
            group_id = f'00000000-0000-4000-8000-{project_id:012d}'
            session.add(AttachmentGroup(id=group_id, user_id=user_id, phase='project'))
            await session.flush()
            session.add(Project(id=project_id, user_id=user_id, group_id=group_id,
                                service_id=service_id, service_title=title,
                                name='Синтетический клиент', description=f'Синтетический проект #{project_id} для проверки кабинета.',
                                status=status, created_at=created_at, updated_at=created_at))

        old = datetime(2020, 1, 1, tzinfo=timezone.utc)
        await project(920001, 92001, 'in_progress', 'Активный проект старше архива', old)
        for index in range(12):
            await project(920010 + index, 92001, 'closed', f'Закрытый проект {index + 1}', old + timedelta(days=index + 1))
        await project(920030, 92002, 'completed', 'Принятый проект из архива', old)
        await project(920031, 92002, 'closed', 'Закрытый проект из архива', old + timedelta(days=1))
        stages = ('new', 'discussing', 'agreed', 'proposal_sent', 'in_progress', 'review', 'completed', 'closed')
        for index, status in enumerate(stages):
            await project(920100 + index, 92006, status, f'Очередь: {status}', old + timedelta(days=30 + index))
        await project(971050, 97105, 'new', 'Материалы', old, service_id=None)


async def main():
    with tempfile.TemporaryDirectory(prefix='nexcora-browser-') as folder:
        url = f'sqlite+aiosqlite:///{Path(folder) / "browser.db"}'
        db = Database(url)
        await db.create_schema()
        await seed_workspace_examples(db)
        settings = Settings(bot_token=BOT_TOKEN, admin_id=999, database_url=url, app_origin='http://127.0.0.1:8765', development=True, frontend_dir=ROOT / 'web' / 'dist', trusted_proxy='127.0.0.1/32')
        app = create_app(settings, database=db, storage=TestStorage(folder))
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=8765, log_level='warning'))
        try: await server.serve()
        finally: await db.close()


if __name__ == '__main__': asyncio.run(main())
