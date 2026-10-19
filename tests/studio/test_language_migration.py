"""The additive locale migration preserves accounts created before localization."""
import os
from contextlib import closing
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest


class LanguageMigrationTests(unittest.TestCase):
    def test_upgrade_populates_existing_accounts_and_remains_reversible(self):
        root = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory(prefix='nexcora-locale-migration-') as folder:
            target = Path(folder) / 'migration.db'
            environment = os.environ.copy()
            environment['DATABASE_URL'] = 'sqlite+aiosqlite:///' + target.as_posix()

            def migrate(revision, direction='upgrade'):
                result = subprocess.run([sys.executable, '-m', 'alembic', direction, revision],
                                        cwd=root, env=environment, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)

            with closing(sqlite3.connect(target)) as connection, connection:
                connection.execute('CREATE TABLE studio_users(id BIGINT PRIMARY KEY, first_name VARCHAR(256) NOT NULL, notifications_enabled BOOLEAN NOT NULL, preference_version INTEGER NOT NULL, data_version INTEGER NOT NULL, created_at DATETIME NOT NULL)')
                connection.execute("INSERT INTO studio_users(id,first_name,notifications_enabled,preference_version,data_version,created_at) VALUES(771,'Existing user',0,4,5,'2026-10-01')")
            # Earlier revisions contain PostgreSQL constraint operations. This
            # disposable old-schema table isolates the new additive migration.
            migrate('f128b628e143', 'stamp')
            migrate('head')
            with closing(sqlite3.connect(target)) as connection, connection:
                self.assertEqual(connection.execute('SELECT first_name,language_code,notifications_enabled,preference_version,data_version FROM studio_users WHERE id=771').fetchone(),
                                 ('Existing user', 'ru', 0, 4, 5))
                connection.execute("UPDATE studio_users SET language_code='kk' WHERE id=771")
            migrate('f128b628e143', 'downgrade')
            with closing(sqlite3.connect(target)) as connection, connection:
                self.assertEqual(connection.execute('SELECT first_name,notifications_enabled FROM studio_users WHERE id=771').fetchone(), ('Existing user', 0))
                self.assertNotIn('language_code', [row[1] for row in connection.execute('PRAGMA table_info(studio_users)')])
            migrate('head')
            with closing(sqlite3.connect(target)) as connection, connection:
                self.assertEqual(connection.execute('SELECT language_code FROM studio_users WHERE id=771').fetchone(), ('ru',))
