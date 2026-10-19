import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from orderbot.database import initialize_database, get_recent_orders


class MigrationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'orders.sqlite3'

    def legacy(self):
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('''CREATE TABLE orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_user_id INTEGER NOT NULL,
                username TEXT, service TEXT NOT NULL, client_name TEXT NOT NULL,
                phone TEXT NOT NULL, comment TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
            db.execute("INSERT INTO orders VALUES (17,123,'old_user','Старая услуга','Имя','+77001234567','Описание','2025-01-01 00:00:00')")
            db.commit()

    async def test_legacy_migration_preserves_order_and_phone(self):
        self.legacy()
        await initialize_database(self.path)
        row = (await get_recent_orders(self.path))[0]
        self.assertEqual(row['id'], 17)
        self.assertEqual(row['phone'], '+77001234567')
        self.assertEqual(row['status'], 'new')
        self.assertIsNone(row['draft_id'])
        self.assertEqual(row['created_at'], '2025-01-01 00:00:00')
        await initialize_database(self.path)
        copies = list((self.path.parent / 'backups').glob('*.sqlite3'))
        self.assertEqual(len(copies), 1)
        with closing(sqlite3.connect(copies[0])) as db:
            self.assertEqual(db.execute('SELECT phone FROM orders').fetchone()[0], '+77001234567')
            self.assertNotIn('status', [r[1] for r in db.execute('PRAGMA table_info(orders)')])
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM notification_outbox').fetchone()[0], 0)

    async def test_backup_failure_leaves_legacy_untouched(self):
        from orderbot import migrations
        self.legacy()
        with patch.object(migrations, 'backup_database', side_effect=OSError('unavailable')):
            with self.assertRaises(OSError):
                await initialize_database(self.path)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertNotIn('status', [r[1] for r in db.execute('PRAGMA table_info(orders)')])
            self.assertEqual(db.execute('SELECT count(*) FROM orders').fetchone()[0], 1)

    async def test_future_schema_is_rejected(self):
        from orderbot.migrations import UnsupportedSchema
        self.legacy()
        with closing(sqlite3.connect(self.path)) as db:
            db.execute('PRAGMA user_version=999')
        with self.assertRaises(UnsupportedSchema):
            await initialize_database(self.path)

    async def test_failed_migration_rolls_back(self):
        from orderbot import migrations
        self.legacy()
        original = migrations.apply_schema
        def broken(db):
            original(db)
            raise RuntimeError('interrupted')
        with patch.object(migrations, 'apply_schema', broken):
            with self.assertRaises(RuntimeError):
                await initialize_database(self.path)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertEqual(db.execute('PRAGMA user_version').fetchone()[0], 0)
            self.assertNotIn('status', [r[1] for r in db.execute('PRAGMA table_info(orders)')])
