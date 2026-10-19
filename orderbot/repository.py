"""Операции SQLite. Соединение принадлежит одной короткой операции."""
import asyncio
from contextlib import closing
from pathlib import Path
import time
from dataclasses import asdict, replace as evolve
from datetime import datetime, timezone
from math import ceil
from .migrations import connect, initialize
from .models import (Draft, Submission, NotFound, Conflict, InvalidInput, Cooldown,
                     AccessDenied, OrderPage, DeleteResult, OutboxEvent, STATUSES, TRANSITIONS)
from uuid import uuid4
from .catalog import get_service
from .validation import clean_name, clean_description


def bump(db, user_id):
    db.execute('INSERT OR IGNORE INTO user_preferences(user_id) VALUES (?)', (user_id,))
    db.execute('UPDATE user_preferences SET data_revision=data_revision+1 WHERE user_id=?', (user_id,))


def enqueue(db, *, key, kind, order_id, recipient, now, status=None, version=None):
    db.execute('''INSERT INTO notification_outbox
        (event_key,kind,order_id,recipient_id,status_value,status_version,next_attempt_at)
        VALUES (?,?,?,?,?,?,?)''', (key, kind, order_id, recipient, status, version, now))


def draft_from(row):
    if row is None: return None
    data = dict(row)
    data['return_to_confirm'] = bool(data['return_to_confirm'])
    return Draft(**data)


def require_admin(actor_id, admin_id):
    if not admin_id or actor_id != admin_id: raise AccessDenied()


def page_offset(page):
    return min(max(0, page), (2**63-1)//5)*5


def preference(db, user_id):
    row = db.execute('SELECT * FROM user_preferences WHERE user_id=?', (user_id,)).fetchone()
    return dict(row) if row else {'notifications_enabled': 1, 'data_revision': 0,
                                  'delete_token': None, 'delete_revision': None,
                                  'delete_expires_at': None}


class Repository:
    def __init__(self, path: Path, *, clock=time.time):
        self.path = Path(path)
        self.clock = clock

    async def initialize(self) -> None:
        await asyncio.to_thread(initialize, self.path)

    async def _run(self, operation, *, write=False):
        def run():
            with closing(connect(self.path)) as db:
                with db:
                    if write:
                        db.execute('BEGIN IMMEDIATE')
                    return operation(db)
        return await asyncio.to_thread(run)

    async def get_draft(self, user_id):
        return await self._run(lambda db: draft_from(db.execute('SELECT * FROM drafts WHERE user_id=?', (user_id,)).fetchone()))

    async def create_draft(self, draft, *, replace=None):
        def operation(db):
            old = db.execute('SELECT * FROM drafts WHERE user_id=?', (draft.user_id,)).fetchone()
            if old:
                if replace != (old['id'], old['revision']): raise Conflict()
                db.execute('DELETE FROM drafts WHERE user_id=?', (draft.user_id,))
            elif replace is not None: raise Conflict()
            saved = evolve(draft, updated_at=self.clock())
            values = asdict(saved)
            db.execute(f"INSERT INTO drafts ({','.join(values)}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))
            bump(db, draft.user_id)
            return saved
        return await self._run(operation, write=True)

    async def update_draft(self, draft, *, expected_revision):
        def operation(db):
            saved = evolve(draft, revision=expected_revision+1, updated_at=self.clock())
            values = asdict(saved)
            updated = db.execute(f"UPDATE drafts SET {','.join(k+'=?' for k in values)} WHERE user_id=? AND id=? AND revision=?",
                                 (*values.values(), draft.user_id, draft.id, expected_revision))
            if updated.rowcount != 1: raise Conflict()
            bump(db, draft.user_id)
            return saved
        return await self._run(operation, write=True)

    async def list_user_orders(self, user_id, *, page=0):
        return await self._list_orders('telegram_user_id=?', (user_id,), page)

    async def _list_orders(self, where, args, page):
        page = max(0, page)
        def operation(db):
            total = db.execute(f'SELECT count(*) FROM orders WHERE {where}', args).fetchone()[0]
            rows = db.execute(f'SELECT * FROM orders WHERE {where} ORDER BY id DESC LIMIT 5 OFFSET ?', (*args,page_offset(page)))
            return OrderPage([dict(row) for row in rows], page, total)
        return await self._run(operation)

    async def get_user_order(self, user_id, order_id):
        def operation(db):
            row = db.execute('SELECT * FROM orders WHERE id=? AND telegram_user_id=?', (order_id,user_id)).fetchone()
            return dict(row) if row else None
        return await self._run(operation)

    async def list_admin_orders(self, actor_id, admin_id, *, status=None, page=0):
        require_admin(actor_id,admin_id)
        if status is not None and status not in STATUSES: raise InvalidInput()
        return await self._list_orders('status=?' if status else '1=1', (status,) if status else (), page)

    async def get_admin_order(self, actor_id, admin_id, order_id):
        require_admin(actor_id,admin_id)
        return await self._get_order(order_id)

    async def _get_order(self, order_id):
        def operation(db):
            row = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
            return dict(row) if row else None
        return await self._run(operation)

    async def admin_summary(self, actor_id, admin_id):
        require_admin(actor_id,admin_id)
        def operation(db):
            result = {status:0 for status in STATUSES}
            result.update({r['status']:r['n'] for r in db.execute('SELECT status,count(*) n FROM orders GROUP BY status')})
            result['all'] = sum(result.values())
            result['failed_notifications'] = db.execute("SELECT count(*) FROM notification_outbox WHERE state='failed'").fetchone()[0]
            return result
        return await self._run(operation)

    async def change_status(self, actor_id, admin_id, order_id, expected_version, status):
        require_admin(actor_id,admin_id)
        def operation(db):
            row = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
            if not row: raise NotFound()
            if row['status_version'] != expected_version: raise Conflict()
            if row['status'] == status: return dict(row)
            if status not in TRANSITIONS.get(row['status'], ()): raise InvalidInput()
            version = expected_version+1
            db.execute('UPDATE orders SET status=?,status_version=? WHERE id=? AND status_version=?', (status,version,order_id,expected_version))
            if preference(db,row['telegram_user_id'])['notifications_enabled']:
                enqueue(db,key=f'order:{order_id}:status:{version}',kind='status_changed',order_id=order_id,
                        recipient=row['telegram_user_id'],now=self.clock(),status=status,version=version)
            bump(db,row['telegram_user_id'])
            return dict(db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone())
        return await self._run(operation, write=True)

    async def get_notifications_enabled(self, user_id):
        return await self._run(lambda db: bool(preference(db,user_id)['notifications_enabled']))

    async def get_user_revision(self, user_id):
        return await self._run(lambda db: preference(db,user_id)['data_revision'])

    async def set_notifications_enabled(self, user_id, enabled, *, expected_revision):
        def operation(db):
            if preference(db,user_id)['data_revision'] != expected_revision: raise Conflict()
            bump(db,user_id)
            db.execute('UPDATE user_preferences SET notifications_enabled=? WHERE user_id=?', (int(enabled),user_id))
            if not enabled:
                db.execute("UPDATE notification_outbox SET state='skipped',error_code='opt_out' WHERE kind='status_changed' AND recipient_id=? AND state IN ('pending','delivering')",(user_id,))
        await self._run(operation,write=True)

    async def prepare_delete(self, user_id):
        def operation(db):
            db.execute('INSERT OR IGNORE INTO user_preferences(user_id) VALUES (?)',(user_id,))
            token = uuid4().hex
            db.execute('UPDATE user_preferences SET delete_token=?,delete_revision=data_revision,delete_expires_at=? WHERE user_id=?', (token,self.clock()+300,user_id))
            return token
        return await self._run(operation,write=True)

    async def cancel_delete(self, user_id, token):
        await self._run(lambda db: db.execute('UPDATE user_preferences SET delete_token=NULL WHERE user_id=? AND delete_token=?',(user_id,token)).rowcount,write=True)

    async def delete_user_data(self, user_id, token):
        def operation(db):
            pref = preference(db,user_id)
            if (not token or pref['delete_token'] != token or pref['delete_revision'] != pref['data_revision']
                    or pref['delete_expires_at'] is None or pref['delete_expires_at'] < self.clock()): raise Conflict()
            count = db.execute('SELECT count(*) FROM notification_outbox WHERE order_id IN (SELECT id FROM orders WHERE telegram_user_id=?)',(user_id,)).fetchone()[0]
            orders = db.execute('DELETE FROM orders WHERE telegram_user_id=?',(user_id,)).rowcount
            drafts = db.execute('DELETE FROM drafts WHERE user_id=?',(user_id,)).rowcount
            db.execute('DELETE FROM user_preferences WHERE user_id=?',(user_id,))
            return DeleteResult(orders,drafts,count)
        return await self._run(operation,write=True)

    async def recover_notifications(self):
        await self._run(lambda db: db.execute("UPDATE notification_outbox SET state='pending' WHERE state='delivering'").rowcount,write=True)

    def _event_payload(self, db, row, admin_id):
        order = db.execute('SELECT * FROM orders WHERE id=?',(row['order_id'],)).fetchone()
        valid = bool(order)
        if row['kind'] == 'new_order':
            valid = valid and bool(admin_id)
            if valid:
                db.execute('UPDATE notification_outbox SET recipient_id=? WHERE id=?',(admin_id,row['id']))
        elif row['kind'] == 'status_changed':
            valid = (valid and preference(db,order['telegram_user_id'])['notifications_enabled']
                     and order['status_version']==row['status_version'] and order['status']==row['status_value'])
        else: valid = False
        if not valid:
            db.execute("UPDATE notification_outbox SET state='skipped',error_code='obsolete' WHERE id=?",(row['id'],))
            return None
        fresh = db.execute('SELECT * FROM notification_outbox WHERE id=?',(row['id'],)).fetchone()
        return OutboxEvent(**dict(fresh)),dict(order)

    async def claim_notification(self, admin_id):
        def operation(db):
            while True:
                row = db.execute("SELECT * FROM notification_outbox WHERE state='pending' AND next_attempt_at<=? ORDER BY id LIMIT 1",(self.clock(),)).fetchone()
                if not row: return None
                if not self._event_payload(db,row,admin_id): continue
                db.execute("UPDATE notification_outbox SET state='delivering',attempts=attempts+1 WHERE id=?",(row['id'],))
                return OutboxEvent(**dict(db.execute('SELECT * FROM notification_outbox WHERE id=?',(row['id'],)).fetchone()))
        return await self._run(operation,write=True)

    async def notification_payload(self, event_id, admin_id):
        def operation(db):
            row = db.execute("SELECT * FROM notification_outbox WHERE id=? AND state='delivering'",(event_id,)).fetchone()
            return self._event_payload(db,row,admin_id) if row else None
        return await self._run(operation,write=True)

    async def record_sent(self, event_id, message_id):
        await self._run(lambda db: db.execute("UPDATE notification_outbox SET state='sent',message_id=?,error_code=NULL WHERE id=? AND state='delivering'",(message_id,event_id)).rowcount,write=True)

    async def record_failure(self, event_id, *, permanent, next_attempt_at, error_code):
        def operation(db):
            row = db.execute("SELECT attempts FROM notification_outbox WHERE id=? AND state='delivering'",(event_id,)).fetchone()
            if not row: return
            state = 'failed' if permanent or row['attempts']>=5 else 'pending'
            db.execute('UPDATE notification_outbox SET state=?,next_attempt_at=?,error_code=? WHERE id=?',
                       (state,next_attempt_at if next_attempt_at is not None else self.clock(),error_code,event_id))
        await self._run(operation,write=True)

    async def list_owner_failures(self, actor_id, admin_id, *, page=0):
        require_admin(actor_id,admin_id)
        def operation(db):
            total = db.execute("SELECT count(*) FROM notification_outbox WHERE state='failed'").fetchone()[0]
            rows = db.execute("SELECT * FROM notification_outbox WHERE state='failed' ORDER BY id DESC LIMIT 5 OFFSET ?",(page_offset(page),))
            return [OutboxEvent(**dict(row)) for row in rows],total
        return await self._run(operation)

    async def retry_owner_event(self, actor_id, admin_id, event_id):
        require_admin(actor_id,admin_id)
        return await self._run(lambda db: db.execute("UPDATE notification_outbox SET state='pending',attempts=0,next_attempt_at=?,recipient_id=?,error_code=NULL WHERE id=? AND state='failed' AND kind='new_order'",(self.clock(),admin_id,event_id)).rowcount==1,write=True)

    async def discard_draft(self, user_id, draft_id, expected_revision):
        def operation(db):
            row = db.execute('SELECT id,revision FROM drafts WHERE user_id=?', (user_id,)).fetchone()
            if not row: return False
            if (row['id'], row['revision']) != (draft_id, expected_revision): raise Conflict()
            db.execute('DELETE FROM drafts WHERE user_id=?', (user_id,))
            bump(db, user_id)
            return True
        return await self._run(operation, write=True)

    async def submit_draft(self, user_id, draft_id, expected_revision, *, username, admin_id):
        def operation(db):
            old = db.execute('SELECT * FROM orders WHERE draft_id=? AND telegram_user_id=?', (draft_id,user_id)).fetchone()
            if old: return Submission(dict(old), False)
            draft = draft_from(db.execute('SELECT * FROM drafts WHERE user_id=? AND id=?', (user_id,draft_id)).fetchone())
            if not draft: raise NotFound()
            if draft.revision != expected_revision: raise Conflict()
            item = get_service(draft.service_id)
            if (draft.step != 'confirm' or not item or not clean_description(draft.description)
                    or not clean_name(draft.name) or len(draft.budget)>80 or len(draft.deadline)>80):
                raise InvalidInput()
            now = self.clock()
            last = db.execute("SELECT max(CAST(strftime('%s',created_at) AS REAL)) FROM orders WHERE telegram_user_id=?", (user_id,)).fetchone()[0]
            if last is not None and now-last < 30: raise Cooldown(ceil(30-(now-last)))
            stamp = datetime.fromtimestamp(now, timezone.utc).strftime('%Y-%m-%d %H:%M:%S')
            cursor = db.execute('''INSERT INTO orders (telegram_user_id,username,service,client_name,phone,comment,
                created_at,draft_id,budget,deadline) VALUES (?,?,?,?,?,?,?,?,?,?)''',
                (user_id,username,item.title,draft.name,'',draft.description,stamp,draft.id,draft.budget,draft.deadline))
            order_id = cursor.lastrowid
            db.execute('DELETE FROM drafts WHERE user_id=?', (user_id,))
            if admin_id:
                enqueue(db,key=f'order:{order_id}:new',kind='new_order',order_id=order_id,recipient=admin_id,now=now)
            bump(db,user_id)
            return Submission(dict(db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()), True)
        return await self._run(operation, write=True)
