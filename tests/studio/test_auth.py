"""Authentication must fail closed for unsigned or expired Telegram identity."""
from datetime import datetime, timezone, timedelta
from dataclasses import replace
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qsl, urlencode
from sqlalchemy import select

from nexcora_studio.auth import verify_init_data, AuthService
from nexcora_studio.errors import DomainError
from nexcora_studio.settings import Settings
from nexcora_studio.db import Database
from nexcora_studio.models import Session
from tests.studio.helpers import signed_init, BOT_TOKEN

NOW = datetime.fromtimestamp(1_800_000_000, timezone.utc)


class SignatureTests(unittest.TestCase):
    def test_valid_signature_uses_authenticated_id(self):
        identity = verify_init_data(signed_init(), BOT_TOKEN, NOW)
        self.assertEqual(identity.user_id, 101)
        self.assertEqual(identity.first_name, 'Алия')

    def test_tampering_expiry_future_duplicates_and_overlarge_input_fail(self):
        cases = [signed_init().replace('101', '202'), signed_init(now=1_799_999_699), signed_init(now=1_800_000_031), signed_init() + '&auth_date=1800000000', 'x=' + 'a' * 16_384, signed_init(user_id=True), signed_init(user_id=-1)]
        for raw in cases:
            with self.subTest(raw=raw[:40]):
                with self.assertRaises(DomainError):
                    verify_init_data(raw, BOT_TOKEN, NOW)


class SessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Database(f'sqlite+aiosqlite:///{Path(self.tmp.name) / "test.db"}')
        await self.db.create_schema()
        self.settings = Settings(bot_token=BOT_TOKEN, admin_id=101, database_url='sqlite+aiosqlite://', app_origin='http://localhost:8000', development=True)
        self.auth = AuthService(self.db, self.settings)

    async def asyncTearDown(self):
        await self.db.close()
        self.tmp.cleanup()

    async def test_token_hash_only_owner_recalculated_and_logout_revokes(self):
        result = await self.auth.login(signed_init(), '127.0.0.1', now=NOW)
        token = result['access_token']
        self.assertTrue((await self.auth.principal(token, now=NOW)).is_owner)
        rotated = AuthService(self.db, replace(self.settings, admin_id=202))
        self.assertFalse((await rotated.principal(token, now=NOW)).is_owner)
        async with self.db.session() as session:
            stored = (await session.scalars(select(Session))).one()
            self.assertNotEqual(stored.token_hash, token)
            self.assertEqual(len(stored.token_hash), 64)
        with self.assertRaises(DomainError):
            await self.auth.principal(token, now=NOW + timedelta(hours=8, seconds=1))
        await self.auth.logout(token)
        with self.assertRaises(DomainError):
            await self.auth.principal(token, now=NOW)

    async def test_invalid_attempts_are_counted_even_when_login_rejected(self):
        for _ in range(30):
            with self.assertRaises(DomainError) as caught:
                await self.auth.login('auth_date=1800000000&hash=bad', '192.0.2.10', now=NOW)
            self.assertEqual(caught.exception.status, 401)
        with self.assertRaises(DomainError) as caught:
            await self.auth.login(signed_init(), '192.0.2.10', now=NOW)
        self.assertEqual(caught.exception.status, 429)
