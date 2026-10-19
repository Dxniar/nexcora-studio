"""Alembic runs once before application processes start."""
import asyncio
import os
from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine
from nexcora_studio.models import Base
from nexcora_studio.runtime import loop_factory

url = os.environ.get('DATABASE_URL', '')
if not url:
    raise RuntimeError('DATABASE_URL is required for migrations')
if url.startswith('postgresql://'):
    url = url.replace('postgresql://', 'postgresql+psycopg://', 1)


def migrate(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    engine = create_async_engine(url, echo=False)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(migrate)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    asyncio.run(online(), loop_factory=loop_factory)
