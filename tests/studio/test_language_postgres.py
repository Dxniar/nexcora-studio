"""Shared preferences retain their locking behavior on the production DB engine."""
import asyncio
import os
import unittest
from nexcora_studio.auth import TelegramIdentity, upsert_telegram_user
from nexcora_studio.models import User
from nexcora_studio.services.privacy import PrivacyService
from tests.studio import test_language, test_postgres


@unittest.skipUnless(os.environ.get('TEST_DATABASE_URL'), 'Dedicated PostgreSQL TEST_DATABASE_URL required')
class PostgresLanguageTests(test_postgres.PostgresMixin, test_language.LanguageTests):
    async def test_concurrent_language_choices_do_not_lose_notification_consent(self):
        privacy = PrivacyService(self.db, self.settings)
        await privacy.set_preferences(self.client, False, 0)
        choices = await asyncio.gather(privacy.set_language(self.client, 'en'), privacy.set_language(self.client, 'kk'))
        self.assertEqual(sorted(user['preference_version'] for user in choices), [2, 3])
        async with self.db.session() as session:
            user = await session.get(User, self.client.user_id)
            self.assertIn(user.language_code, ('en', 'kk'))
            self.assertFalse(user.notifications_enabled)
            self.assertEqual(user.preference_version, 3)

    async def test_telegram_upsert_does_not_overwrite_a_saved_language(self):
        privacy = PrivacyService(self.db, self.settings)
        await privacy.set_language(self.client, 'kk')
        async with self.db.session() as session:
            user = await upsert_telegram_user(session, self.db.engine.dialect.name, TelegramIdentity(101, 'Updated', None, 'en'))
            self.assertEqual(user.language_code, 'kk')
        async with self.db.session() as session:
            user = await session.get(User, 101)
            self.assertEqual((user.language_code, user.first_name), ('kk', 'Updated'))
