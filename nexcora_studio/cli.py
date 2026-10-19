"""Explicit database administration; never runs bot polling."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from .db import Database
from .legacy_import import import_legacy
from .runtime import loop_factory


def main():
    parser = argparse.ArgumentParser(description='Nexcora Studio database operations')
    actions = parser.add_subparsers(dest='command', required=True)
    actions.add_parser('migrate')
    actions.add_parser('check')
    importer = actions.add_parser('import-sqlite')
    importer.add_argument('--source', type=Path, required=True)
    importer.add_argument('--apply', action='store_true', help='Apply after checking an empty target; default is dry-run')
    args = parser.parse_args()
    url = os.environ.get('DATABASE_URL')
    if not url: parser.error('DATABASE_URL is required')
    if args.command == 'migrate':
        command.upgrade(Config(str(Path(__file__).resolve().parent.parent / 'alembic.ini')), 'head')
        print('Database migrated to head')
    elif args.command == 'import-sqlite':
        result = asyncio.run(import_legacy(args.source, url, dry_run=not args.apply), loop_factory=loop_factory)
        print(json.dumps(result, ensure_ascii=False))
    else:
        async def check():
            database = Database(url)
            try:
                async with database.session() as session:
                    await session.execute(text('SELECT 1 FROM studio_projects LIMIT 1'))
            finally:
                await database.close()
        asyncio.run(check(), loop_factory=loop_factory)
        print('Database connection and schema: OK')


if __name__ == '__main__':
    main()
