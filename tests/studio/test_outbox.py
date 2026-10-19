"""Durable delivery only; retries never repeat project business operations."""
import asyncio
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import os
import unittest
from sqlalchemy import func, select
from nexcora_studio.auth import Principal, as_utc
from nexcora_studio.errors import DomainError
from nexcora_studio.models import Event, Outbox, Project, User
from nexcora_studio.services.projects import ProjectService
from nexcora_studio.services.privacy import PrivacyService
from nexcora_studio.runtime import loop_factory
from tests.studio.cases import StudioCase
from tests.studio.pg_sandbox import PgSandbox


class SyntheticSender:
    def __init__(self, failure=None, before_send=None):
        self.failure, self.before_send, self.deliveries = failure, before_send, []

    async def send(self, notification):
        if self.before_send: await self.before_send()
        self.deliveries.append(notification)
        if self.failure: raise self.failure
        return 700 + len(self.deliveries)


class OutboxTests(StudioCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.now = datetime(2026, 10, 18, 12, tzinfo=timezone.utc)
        self.portal = ProjectService(self.db, self.settings, clock=lambda: self.now)
        draft = await self.portal.get_draft(self.client)
        draft = await self.portal.save_draft(self.client, {'service_id': 'bot', 'name': 'Алия', 'description': 'Бот для записи клиентов'}, draft['version'])
        self.project = await self.portal.submit(self.client, draft['id'], draft['version'], 0, 'submit')
        async with self.db.session() as session:
            self.event_id = await session.scalar(select(Outbox.id))

    def worker(self, sender=None, settings=None, **kwargs):
        from nexcora_studio.outbox import OutboxWorker
        return OutboxWorker(self.db, settings or self.settings, sender or SyntheticSender(), clock=lambda: self.now, **kwargs)

    async def row(self):
        async with self.db.session() as session: return await session.get(Outbox, self.event_id)

    async def client_event(self):
        async with self.db.session() as session:
            event = await session.get(Outbox, self.event_id)
            event.recipient_role, event.recipient_id = 'client', 101

    async def test_send_marks_delivery_and_does_not_change_project_history(self):
        sender = SyntheticSender()
        self.assertEqual(await self.worker(sender).run_once(), 1)
        row = await self.row()
        self.assertEqual((row.state, row.attempts, row.message_id), ('sent', 1, 701))
        self.assertIsNone(row.worker_id)
        self.assertEqual(sender.deliveries[0].url, 'http://127.0.0.1:8000/owner/projects/1')
        async with self.db.session() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(Event)), 1)
            self.assertEqual((await session.get(Project, self.project['id'])).version, self.project['version'])

    async def test_claim_does_not_steal_live_lease_but_recovers_expired(self):
        first, second = self.worker(), self.worker()
        self.assertEqual(await first.claim_events(first.worker_id), [self.event_id])
        self.assertEqual(await second.claim_events(second.worker_id), [])
        self.now += timedelta(seconds=61)
        self.assertEqual(await second.claim_events(second.worker_id), [self.event_id])
        self.assertEqual((await self.row()).attempts, 2)
        # A delayed response from the first process cannot acknowledge the new lease.
        await first._sent(self.event_id, 900)
        self.assertEqual((await self.row()).worker_id, second.worker_id)

    async def test_transient_failures_use_schedule_and_stop_after_five_attempts(self):
        from nexcora_studio.outbox import DeliveryFailure
        sender = SyntheticSender(DeliveryFailure('temporary'))
        worker = self.worker(sender)
        for attempt, delay in enumerate((10, 60, 300, 1800), 1):
            await worker.run_once()
            row = await self.row()
            self.assertEqual((row.state, row.attempts), ('pending', attempt))
            self.assertEqual(as_utc(row.next_attempt_at), self.now + timedelta(seconds=delay))
            self.assertEqual(await worker.run_once(), 0)
            self.now += timedelta(seconds=delay)
        await worker.run_once()
        self.assertEqual(((await self.row()).state, (await self.row()).attempts), ('failed', 5))
        self.now += timedelta(days=1)
        self.assertEqual(await worker.run_once(), 0)
        self.assertEqual(len(sender.deliveries), 5)

    async def test_retry_after_and_permanent_failure(self):
        from nexcora_studio.outbox import DeliveryFailure
        sender = SyntheticSender(DeliveryFailure('retry_after', retry_after=172800))
        worker = self.worker(sender)
        await worker.run_once()
        self.assertEqual(as_utc((await self.row()).next_attempt_at), self.now + timedelta(seconds=172800))
        self.now += timedelta(seconds=172800)
        sender.failure = DeliveryFailure('forbidden', permanent=True)
        await worker.run_once()
        self.assertEqual(((await self.row()).state, (await self.row()).error_code), ('failed', 'forbidden'))

    async def test_lost_response_can_repeat_message_but_not_business_event(self):
        from nexcora_studio.outbox import DeliveryFailure
        sender = SyntheticSender(DeliveryFailure('temporary'))
        worker = self.worker(sender)
        await worker.run_once()
        sender.failure = None
        self.now += timedelta(seconds=10)
        await worker.run_once()
        self.assertEqual(len(sender.deliveries), 2)
        self.assertEqual((await self.row()).state, 'sent')
        async with self.db.session() as session:
            self.assertEqual(await session.scalar(select(func.count()).select_from(Event)), 1)
            self.assertEqual((await session.get(Project, self.project['id'])).version, self.project['version'])

    async def test_notification_api_uses_real_auth_and_owner_scope(self):
        import httpx
        from nexcora_studio.app import create_app
        from nexcora_studio.outbox import DeliveryFailure
        from tests.studio.helpers import signed_init
        await self.worker(SyntheticSender(DeliveryFailure('forbidden', permanent=True))).run_once()
        app = create_app(self.settings, database=self.db)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=self.settings.app_origin) as http:
            owner = await http.post('/api/v1/auth/telegram', json={'init_data': signed_init(999, int(datetime.now(timezone.utc).timestamp()))})
            client = await http.post('/api/v1/auth/telegram', json={'init_data': signed_init(101, int(datetime.now(timezone.utc).timestamp()))})
            owner_headers = {'Authorization': 'Bearer ' + owner.json()['access_token']}
            client_headers = {'Authorization': 'Bearer ' + client.json()['access_token']}
            listing = await http.get('/api/v1/owner/notifications', headers=owner_headers)
            self.assertEqual(listing.status_code, 200)
            self.assertEqual(listing.json()['items'][0]['id'], self.event_id)
            forbidden = await http.post(f'/api/v1/owner/notifications/{self.event_id}/retry', headers=client_headers)
            self.assertEqual(forbidden.status_code, 403)
            retry = await http.post(f'/api/v1/owner/notifications/{self.event_id}/retry', headers=owner_headers)
            self.assertEqual((retry.status_code, retry.json()['state']), (200, 'pending'))
            self.assertEqual((await http.get('/api/v1/owner/notifications', headers=owner_headers)).json()['items'], [])

    async def test_legacy_history_never_auto_dispatches(self):
        async with self.db.session() as session:
            (await session.get(Outbox, self.event_id)).legacy_event_key = 'old:1'
        sender = SyntheticSender()
        self.assertEqual(await self.worker(sender).run_once(), 0)
        self.assertEqual(sender.deliveries, [])

    async def test_stale_project_version_is_cancelled(self):
        async with self.db.session() as session: (await session.get(Project, self.project['id'])).version += 1
        sender = SyntheticSender()
        await self.worker(sender).run_once()
        self.assertEqual((await self.row()).state, 'cancelled')
        self.assertEqual(sender.deliveries, [])

    async def test_owner_rotation_does_not_send_to_previous_owner(self):
        sender = SyntheticSender()
        await self.worker(sender, settings=replace(self.settings, admin_id=202)).run_once()
        self.assertEqual((await self.row()).state, 'cancelled')
        self.assertEqual(sender.deliveries, [])

    async def test_client_opt_out_during_failure_never_resurrects_event(self):
        from nexcora_studio.outbox import DeliveryFailure
        await self.client_event()
        privacy = PrivacyService(self.db, self.settings)
        async def opt_out(): await privacy.set_preferences(self.client, False, 0)
        sender = SyntheticSender(DeliveryFailure('temporary'), opt_out)
        await self.worker(sender).run_once()
        self.assertEqual((await self.row()).state, 'cancelled')

    async def test_exhausted_crashed_delivery_becomes_failed_without_sending(self):
        async with self.db.session() as session:
            row = await session.get(Outbox, self.event_id)
            row.state, row.attempts = 'delivering', 5
            row.lease_until, row.worker_id = self.now - timedelta(seconds=1), 'dead-worker'
        sender = SyntheticSender()
        await self.worker(sender).run_once()
        self.assertEqual((await self.row()).state, 'failed')
        self.assertEqual(sender.deliveries, [])

    async def test_sender_deadline_preserves_bounded_retry(self):
        class SlowSender:
            async def send(self, notification): await asyncio.Event().wait()
        await self.worker(SlowSender(), send_timeout=0.01).run_once()
        row = await self.row()
        self.assertEqual((row.state, row.error_code), ('pending', 'timeout'))

    async def test_cancellation_keeps_lease_until_expiry(self):
        started = asyncio.Event()
        class WaitingSender:
            async def send(self, notification):
                started.set()
                await asyncio.Event().wait()
        worker = self.worker(WaitingSender())
        task = asyncio.create_task(worker.run_once())
        await asyncio.wait_for(started.wait(), timeout=2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError): await task
        row = await self.row()
        self.assertEqual((row.state, row.worker_id), ('delivering', worker.worker_id))
        self.assertEqual(await self.worker().claim_events('replacement'), [])

    async def test_failed_listing_and_retry_enforce_current_owner_and_are_idempotent(self):
        from nexcora_studio.outbox import DeliveryFailure, OutboxService
        await self.worker(SyntheticSender(DeliveryFailure('forbidden', permanent=True))).run_once()
        service = OutboxService(self.db, self.settings, clock=lambda: self.now)
        with self.assertRaises(DomainError) as denied: await service.retry(self.client, self.event_id)
        self.assertEqual(denied.exception.status, 403)
        items = await service.list_failed(self.owner)
        self.assertEqual([(x['id'], x['attempts'], x['error_code']) for x in items['items']], [(self.event_id, 1, 'forbidden')])
        first = await service.retry(self.owner, self.event_id)
        second = await service.retry(self.owner, self.event_id)
        self.assertEqual((first['state'], second['state']), ('pending', 'pending'))
        self.assertEqual((await self.row()).attempts, 0)
        async with self.db.session() as session: self.assertEqual(await session.scalar(select(func.count()).select_from(Event)), 1)
        rotated = OutboxService(self.db, replace(self.settings, admin_id=202), clock=lambda: self.now)
        with self.assertRaises(DomainError) as denied: await rotated.list_failed(Principal(999, True))
        self.assertEqual(denied.exception.status, 403)

    async def test_manual_retry_rejects_stale_legacy_and_opted_out_events(self):
        from nexcora_studio.outbox import OutboxService
        service = OutboxService(self.db, self.settings, clock=lambda: self.now)
        for change in ('version', 'legacy', 'optout'):
            async with self.db.session() as session:
                row = await session.get(Outbox, self.event_id)
                row.state, row.legacy_event_key = 'failed', None
                row.project_version = self.project['version']
                row.recipient_id, row.recipient_role = 101, 'client'
                (await session.get(User, 101)).notifications_enabled = change != 'optout'
                if change == 'legacy': row.legacy_event_key = 'old:1'
                if change == 'version': row.project_version -= 1
            with self.assertRaises(DomainError) as invalid: await service.retry(self.owner, self.event_id)
            self.assertEqual(invalid.exception.status, 409)


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Dedicated PostgreSQL TEST_DATABASE_URL required')
class PostgresOutboxTests(OutboxTests):
    loop_factory = staticmethod(loop_factory)

    async def target_url(self):
        self.pg = PgSandbox()
        return await self.pg.start()

    async def test_concurrent_claims_choose_each_event_once(self):
        first, second = self.worker(), self.worker()
        claims = await asyncio.gather(first.claim_events(first.worker_id), second.claim_events(second.worker_id))
        self.assertEqual(sorted(map(len, claims)), [0, 1])
        self.assertEqual((await self.row()).attempts, 1)

    async def test_locked_row_does_not_block_other_due_delivery(self):
        async with self.db.session() as session:
            event = Event(project_id=self.project['id'], actor_id=101, kind='update')
            session.add(event)
            await session.flush()
            row = Outbox(event_id=event.id, project_id=self.project['id'], kind='update', recipient_id=999,
                         recipient_role='owner', project_version=self.project['version'], next_attempt_at=self.now)
            session.add(row)
            await session.flush()
            second_id = row.id
        async with self.db.session() as locked_session:
            await locked_session.scalar(select(Outbox).where(Outbox.id == self.event_id).with_for_update())
            worker = self.worker()
            claimed = await asyncio.wait_for(worker.claim_events(worker.worker_id), timeout=2)
            self.assertEqual(claimed, [second_id])
