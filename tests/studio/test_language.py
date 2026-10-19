"""Language is an authenticated shared preference, independent of notification consent."""
from datetime import datetime, timezone
import json
import httpx
from nexcora_studio.app import create_app
from nexcora_studio.models import User
from tests.studio.cases import StudioCase
from tests.studio.fakes import MemoryStorage
from tests.studio.helpers import signed_init


class LanguageTests(StudioCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.app = create_app(self.settings, database=self.db, storage=MemoryStorage())
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url=self.settings.app_origin)

    async def asyncTearDown(self):
        await self.http.aclose()
        await super().asyncTearDown()

    async def login(self, user_id=101, language='ru', name='Алия'):
        raw = signed_init(user_id, int(datetime.now(timezone.utc).timestamp()),
                          user=json.dumps({'id': user_id, 'first_name': name, 'language_code': language}))
        response = await self.http.post('/api/v1/auth/telegram', json={'init_data': raw})
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        return {'Authorization': 'Bearer ' + result['access_token']}, result['user']

    async def test_new_user_detects_supported_telegram_language_and_falls_back(self):
        for user_id, telegram_language, expected in [(301, 'en-GB', 'en'), (302, 'kk', 'kk'), (303, 'de', 'ru'), (304, None, 'ru')]:
            with self.subTest(language=telegram_language):
                headers, user = await self.login(user_id, telegram_language)
                self.assertEqual(user.get('language_code'), expected)
                self.assertEqual((await self.http.get('/api/v1/me', headers=headers)).json()['language_code'], expected)

    async def test_saved_language_survives_new_sessions_and_telegram_language_changes(self):
        headers, old_user = await self.login()
        changed = await self.http.put('/api/v1/me/language', headers=headers, json={'language_code': 'kk'})
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()['language_code'], 'kk')
        new_headers, user = await self.login(language='en', name='Updated name')
        self.assertEqual(user['language_code'], 'kk')
        self.assertEqual(user['first_name'], 'Updated name')
        self.assertEqual((await self.http.get('/api/v1/me', headers=headers)).json()['language_code'], 'kk')
        self.assertEqual((await self.http.get('/api/v1/me', headers=new_headers)).json()['language_code'], 'kk')

    async def test_language_endpoint_rejects_unauthenticated_invalid_and_foreign_fields(self):
        self.assertEqual((await self.http.put('/api/v1/me/language', json={'language_code': 'en'})).status_code, 401)
        headers, _ = await self.login()
        for body in [{'language_code': 'de'}, {'language_code': 'EN'}, {'language_code': ''}, {'language_code': None}, {'language_code': True}, {'language_code': 'en', 'user_id': 202}]:
            with self.subTest(body=body):
                response = await self.http.put('/api/v1/me/language', headers=headers, json=body)
                self.assertEqual(response.status_code, 422, response.text)
        async with self.db.session() as session:
            self.assertEqual((await session.get(User, 101)).language_code, 'ru')
            self.assertEqual((await session.get(User, 202)).language_code, 'ru')

    async def test_language_does_not_reenable_notifications_or_invalidate_session(self):
        headers, _ = await self.login()
        disabled = await self.http.put('/api/v1/me/preferences', headers=headers, json={'notifications_enabled': False, 'expected_version': 0})
        self.assertEqual(disabled.status_code, 200, disabled.text)
        response = await self.http.put('/api/v1/me/language', headers=headers, json={'language_code': 'en'})
        self.assertEqual(response.status_code, 200, response.text)
        user = response.json()
        self.assertFalse(user['notifications_enabled'])
        self.assertEqual(user['preference_version'], 2)
        self.assertEqual((await self.http.get('/api/v1/me', headers=headers)).status_code, 200)
        stale = await self.http.put('/api/v1/me/preferences', headers=headers, json={'notifications_enabled': True, 'expected_version': 1})
        self.assertEqual(stale.status_code, 409)
        current = await self.http.put('/api/v1/me/preferences', headers=headers, json={'notifications_enabled': True, 'expected_version': user['preference_version']})
        self.assertEqual(current.status_code, 200)
        self.assertEqual(current.json()['language_code'], 'en')

    async def test_existing_owner_and_client_preferences_are_isolated(self):
        client, _ = await self.login()
        owner, _ = await self.login(999)
        for headers, language in [(owner, 'en'), (client, 'kk')]:
            response = await self.http.put('/api/v1/me/language', headers=headers, json={'language_code': language})
            self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual((await self.http.get('/api/v1/me', headers=owner)).json()['language_code'], 'en')
        self.assertEqual((await self.http.get('/api/v1/me', headers=client)).json()['language_code'], 'kk')
