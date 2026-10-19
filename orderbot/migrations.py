"""Транзакционная схема v2; рабочие данные здесь не сбрасываются."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from uuid import uuid4

SCHEMA_VERSION = 2


class UnsupportedSchema(Exception): pass


def connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def backup_database(db: sqlite3.Connection, path: Path) -> None:
    folder = path.parent / 'backups'
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
    destination = folder / f'{path.stem}-v0-{stamp}-{uuid4().hex[:8]}.sqlite3'
    with closing(sqlite3.connect(destination)) as copy:
        db.backup(copy)


def apply_schema(db: sqlite3.Connection) -> None:
    db.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, telegram_user_id INTEGER NOT NULL,
        username TEXT, service TEXT NOT NULL, client_name TEXT NOT NULL,
        phone TEXT NOT NULL, comment TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)''')
    columns = {row['name'] for row in db.execute('PRAGMA table_info(orders)')}
    additions = {'draft_id': 'TEXT', 'budget': "TEXT NOT NULL DEFAULT ''",
                 'deadline': "TEXT NOT NULL DEFAULT ''", 'status': "TEXT NOT NULL DEFAULT 'new'",
                 'status_version': 'INTEGER NOT NULL DEFAULT 0'}
    for name, declaration in additions.items():
        if name not in columns:
            db.execute(f'ALTER TABLE orders ADD COLUMN {name} {declaration}')
    db.execute('CREATE UNIQUE INDEX IF NOT EXISTS idx_order_draft ON orders(draft_id)')
    db.execute('CREATE INDEX IF NOT EXISTS idx_orders_user_id ON orders(telegram_user_id)')
    db.execute('''CREATE TABLE IF NOT EXISTS drafts (
        id TEXT NOT NULL UNIQUE, user_id INTEGER PRIMARY KEY, service_id TEXT,
        description TEXT NOT NULL DEFAULT '', budget TEXT NOT NULL DEFAULT '',
        deadline TEXT NOT NULL DEFAULT '', name TEXT NOT NULL DEFAULT '',
        step TEXT NOT NULL DEFAULT 'service', return_to_confirm INTEGER NOT NULL DEFAULT 0,
        revision INTEGER NOT NULL DEFAULT 0, updated_at REAL NOT NULL)''')
    db.execute('''CREATE TABLE IF NOT EXISTS notification_outbox (
        id INTEGER PRIMARY KEY AUTOINCREMENT, event_key TEXT NOT NULL UNIQUE,
        kind TEXT NOT NULL, order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
        recipient_id INTEGER NOT NULL, status_value TEXT, status_version INTEGER,
        state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
        next_attempt_at REAL NOT NULL, message_id INTEGER, error_code TEXT)''')
    db.execute('CREATE INDEX IF NOT EXISTS idx_outbox_due ON notification_outbox(state,next_attempt_at)')
    db.execute('''CREATE TABLE IF NOT EXISTS user_preferences (
        user_id INTEGER PRIMARY KEY, notifications_enabled INTEGER NOT NULL DEFAULT 1,
        data_revision INTEGER NOT NULL DEFAULT 0, delete_token TEXT,
        delete_revision INTEGER, delete_expires_at REAL)''')


def initialize(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(connect(path)) as db:
        version = db.execute('PRAGMA user_version').fetchone()[0]
        if version > SCHEMA_VERSION:
            raise UnsupportedSchema('База создана более новой версией Nexcora.')
        if version == SCHEMA_VERSION:
            return
        existing = db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='orders'").fetchone()
        if existing:
            backup_database(db, path)
        with db:
            db.execute('BEGIN IMMEDIATE')
            apply_schema(db)
            db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')
