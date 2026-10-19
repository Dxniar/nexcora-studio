"""One async SQL transaction per application operation."""
from contextlib import asynccontextmanager
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class Database:
    def __init__(self, url: str):
        if url.startswith('postgresql://'):
            url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
        options = {'connect_args': {'connect_timeout': 5}, 'pool_timeout': 5} if url.startswith('postgresql+') else {}
        self.engine = create_async_engine(url, echo=False, pool_pre_ping=True, **options)
        if self.engine.dialect.name == 'sqlite':
            @event.listens_for(self.engine.sync_engine, 'connect')
            def enable_foreign_keys(connection, _):
                cursor = connection.cursor()
                cursor.execute('PRAGMA foreign_keys=ON')
                cursor.close()
        self._factory = async_sessionmaker(self.engine, expire_on_commit=False)

    @asynccontextmanager
    async def session(self):
        async with self._factory() as session:
            async with session.begin():
                yield session

    async def create_schema(self):
        """Bootstrap disposable local databases; production uses Alembic."""
        from .models import Base
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def close(self):
        await self.engine.dispose()
