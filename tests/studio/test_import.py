"""Historical orders must retain data without fabricated agreements or sends."""
from datetime import datetime, timezone
from contextlib import closing
import hashlib
import sqlite3
import tempfile
import unittest
from pathlib import Path
from sqlalchemy import select, func
from nexcora_studio.db import Database
from nexcora_studio.models import Project, User, Draft, Outbox, DeletionConfirmation
from nexcora_studio.legacy_import import import_legacy


class ImportTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.source = Path(self.tmp.name) / 'old.db'
        self.url = await self.target_url()
        self.db = Database(self.url)
        await self.db.create_schema()
        with closing(sqlite3.connect(self.source)) as old, old:
            old.execute('CREATE TABLE orders(id INTEGER PRIMARY KEY, telegram_user_id INTEGER, username TEXT, service TEXT, client_name TEXT, phone TEXT, comment TEXT, created_at TEXT)')
            old.execute('INSERT INTO orders VALUES (9001, 112233445566, NULL, ?, ?, ?, ?, ?)', ('Исходная услуга', 'Клиент', '+77001234567', 'Исторический текст', '2024-01-02 03:04:05'))

    async def asyncTearDown(self):
        await self.db.close()
        self.tmp.cleanup()
        if hasattr(self, 'pg'): await self.pg.close()

    async def target_url(self):
        return f'sqlite+aiosqlite:///{Path(self.tmp.name) / "new.db"}'

    async def test_dry_run_no_writes_and_import_keeps_id_text_date_and_source(self):
        before = hashlib.sha256(self.source.read_bytes()).hexdigest()
        report = await import_legacy(self.source, self.url, dry_run=True)
        self.assertEqual(report['projects'], 1)
        async with self.db.session() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(Project)), 0)
        await import_legacy(self.source, self.url, dry_run=False)
        async with self.db.session() as session:
            order = await session.get(Project, 9001)
            self.assertEqual((order.workflow, order.service_id, order.service_title), ('legacy', None, 'Исходная услуга'))
            self.assertEqual(order.phone, '+77001234567')
            self.assertEqual(order.description, 'Исторический текст')
            from nexcora_studio.auth import as_utc
            self.assertEqual(as_utc(order.created_at), datetime(2024, 1, 2, 3, 4, 5, tzinfo=timezone.utc))
            self.assertIsNone(order.accepted_proposal_version)
            self.assertEqual(await session.scalar(select(func.count()).select_from(Outbox)), 0)
        self.assertEqual(hashlib.sha256(self.source.read_bytes()).hexdigest(), before)
        with self.assertRaises(ValueError):
            await import_legacy(self.source, self.url, dry_run=False)

    async def test_invalid_record_aborts_entire_import(self):
        with closing(sqlite3.connect(self.source)) as old, old:
            old.execute("INSERT INTO orders VALUES (9002, 22, NULL, 'Broken', '', '', '', 'invalid date')")
        with self.assertRaises(ValueError):
            await import_legacy(self.source, self.url, dry_run=False)
        async with self.db.session() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(User)), 0)

    async def test_v2_partial_draft_preferences_and_frozen_outbox_preserved(self):
        from orderbot.migrations import apply_schema
        with closing(sqlite3.connect(self.source)) as old, old:
            old.row_factory = sqlite3.Row
            apply_schema(old)
            old.execute("PRAGMA user_version=2")
            old.execute("UPDATE orders SET budget='Обсудим отдельно',deadline='После сессии',status='closed',status_version=7")
            old.execute("INSERT INTO drafts(id,user_id,service_id,description,name,step,revision,return_to_confirm,updated_at) VALUES ('legacy-draft',202,'bot','','А','confirm',4,1,1700000000)")
            old.execute("INSERT INTO user_preferences(user_id,notifications_enabled,data_revision,delete_token,delete_revision,delete_expires_at) VALUES(404,0,8,'old-plaintext-token',8,1900000000)")
            old.execute("INSERT INTO notification_outbox(id,event_key,kind,order_id,recipient_id,status_value,status_version,state,attempts,next_attempt_at) VALUES(51,'historical-event','status_changed',9001,112233445566,'closed',7,'pending',3,1700000000)")
        await import_legacy(self.source, self.url, dry_run=False)
        async with self.db.session() as session:
            project = await session.get(Project, 9001)
            self.assertEqual((project.budget, project.deadline, project.status, project.version), ('Обсудим отдельно', 'После сессии', 'closed', 7))
            draft = await session.get(Draft, 'legacy-draft')
            self.assertEqual((draft.fields['name'], draft.legacy_step, draft.legacy_return_to_confirm, draft.version), ('А', 'confirm', True, 4))
            user = await session.get(User, 404)
            self.assertFalse(user.notifications_enabled)
            self.assertEqual(user.data_version, 8)
            notification = await session.get(Outbox, 51)
            self.assertEqual((notification.legacy_event_key, notification.state, notification.attempts), ('historical-event', 'pending', 3))
            self.assertFalse(notification.legacy_metadata['automatic_delivery'])
            self.assertEqual(await session.scalar(select(func.count()).select_from(DeletionConfirmation)), 0)
