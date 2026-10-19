"""Random schemas in a specifically named test DB; never touch existing schemas."""
import os
import re
from uuid import uuid4
from sqlalchemy import text
from sqlalchemy.engine import make_url
from nexcora_studio.db import Database


class PgSandbox:
    async def start(self):
        base = make_url(os.environ['TEST_DATABASE_URL'])
        if not (base.database.endswith('_test') or base.database.startswith('test_')):
            raise ValueError('TEST_DATABASE_URL database name must end in _test or begin with test_')
        self.admin = Database(base.render_as_string(hide_password=False))
        self.schema = 'nexcora_test_' + uuid4().hex
        async with self.admin.session() as session:
            await session.execute(text(f'CREATE SCHEMA "{self.schema}"'))
        self.url = base.update_query_dict({'options': '-csearch_path=' + self.schema}).render_as_string(hide_password=False)
        return self.url

    async def close(self):
        if not re.fullmatch(r'nexcora_test_[0-9a-f]{32}', self.schema): raise ValueError('Invalid disposable schema')
        try:
            async with self.admin.session() as session:
                await session.execute(text(f'DROP SCHEMA "{self.schema}" CASCADE'))
        finally:
            await self.admin.close()
