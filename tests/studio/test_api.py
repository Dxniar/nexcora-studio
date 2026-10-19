from datetime import datetime, timezone
import httpx
from nexcora_studio.app import create_app
from tests.studio.cases import StudioCase
from tests.studio.helpers import signed_init
from tests.studio.fakes import MemoryStorage


class ApiTests(StudioCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.app = create_app(self.settings, database=self.db, storage=MemoryStorage())
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=self.app), base_url=self.settings.app_origin)

    async def asyncTearDown(self):
        await self.http.aclose()
        await super().asyncTearDown()

    async def headers(self, user_id=101):
        response = await self.http.post('/api/v1/auth/telegram', json={'init_data': signed_init(user_id, int(datetime.now(timezone.utc).timestamp()))})
        self.assertEqual(response.status_code, 200, response.text)
        return {'Authorization': 'Bearer ' + response.json()['access_token']}

    async def test_login_draft_submit_and_owner_scope_roundtrip(self):
        headers = await self.headers()
        owner = await self.headers(999)
        draft = (await self.http.get('/api/v1/me/draft', headers=headers)).json()
        saved = await self.http.put('/api/v1/me/draft', headers=headers, json={'expected_version': draft['version'], 'fields': {'name': 'Алия', 'description': 'Бот для записи клиентов', 'service_id': 'bot'}})
        self.assertEqual(saved.status_code, 200, saved.text)
        submitted = await self.http.post('/api/v1/me/draft/submit', headers=headers | {'Idempotency-Key': 'http-submit'}, json={'draft_id': draft['id'], 'expected_version': saved.json()['version'], 'attachments_version': 0})
        self.assertEqual(submitted.status_code, 200, submitted.text)
        queue = await self.http.get('/api/v1/owner/projects', headers=owner)
        self.assertEqual(queue.json()['total'], 1)
        self.assertEqual((await self.http.get('/api/v1/owner/projects', headers=headers)).status_code, 403)
        foreign = await self.headers(202)
        self.assertEqual((await self.http.get(f'/api/v1/me/projects/{submitted.json()["id"]}', headers=foreign)).status_code, 404)

    async def test_unauthenticated_invalid_origin_and_oversized_json_rejected(self):
        self.assertEqual((await self.http.get('/api/v1/me')).status_code, 401)
        response = await self.http.post('/api/v1/auth/telegram', headers={'Origin': 'https://foreign.test'}, json={'init_data': 'secret-payload'})
        self.assertEqual(response.status_code, 403)
        response = await self.http.post('/api/v1/auth/telegram', content=b'x' * 65_537, headers={'Content-Type': 'application/json'})
        self.assertEqual(response.status_code, 413)
        self.assertNotIn('secret-payload', response.text)
        self.assertIn('request_id', response.json()['error'])

    async def test_logout_revokes_session_and_errors_do_not_echo_credentials(self):
        headers = await self.headers()
        response = await self.http.post('/api/v1/auth/logout', headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual((await self.http.get('/api/v1/me', headers=headers)).status_code, 401)
        response = await self.http.post('/api/v1/auth/telegram', json={'init_data': 'not-a-signed-secret'})
        self.assertEqual(response.status_code, 401)
        self.assertNotIn('not-a-signed-secret', response.text)
        self.assertIn('nosniff', response.headers['x-content-type-options'])

    async def test_file_private_download_headers_and_owner_only_after_submit(self):
        headers = await self.headers()
        owner = await self.headers(999)
        draft = (await self.http.get('/api/v1/me/draft', headers=headers)).json()
        data = b'Project brief text'
        reservation = await self.http.post('/api/v1/me/draft/attachments', headers=headers | {'Idempotency-Key': 'file-http'}, json={'filename': 'brief.txt', 'size_bytes': len(data), 'expected_attachments_version': 0})
        self.assertEqual(reservation.status_code, 200, reservation.text)
        file_id = reservation.json()['id']
        uploaded = await self.http.put(f'/api/v1/attachments/{file_id}/content', headers=headers, content=data)
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        url = f'/api/v1/attachments/{file_id}/download'
        self.assertEqual((await self.http.get(url, headers=owner)).status_code, 404)
        downloaded = await self.http.get(url, headers=headers)
        self.assertEqual(downloaded.content, data)
        self.assertIn('attachment;', downloaded.headers['content-disposition'])
        self.assertEqual(downloaded.headers['content-type'], 'application/octet-stream')
        self.assertIn('no-store', downloaded.headers['cache-control'])
        saved = await self.http.put('/api/v1/me/draft', headers=headers, json={'expected_version': 0, 'fields': {'name': 'Алия', 'service_id': 'bot', 'description': 'Бот для записи на услуги'}})
        current = (await self.http.get('/api/v1/me/draft', headers=headers)).json()
        sent = await self.http.post('/api/v1/me/draft/submit', headers=headers | {'Idempotency-Key': 'send-with-file'}, json={'draft_id': draft['id'], 'expected_version': saved.json()['version'], 'attachments_version': current['attachments']['version']})
        self.assertEqual(sent.status_code, 200, sent.text)
        self.assertEqual((await self.http.get(url, headers=owner)).content, data)
        self.assertEqual((await self.http.delete(f'/api/v1/attachments/{file_id}', headers=headers)).status_code, 409)

    async def test_unauthenticated_raw_upload_is_rejected_before_stream_read(self):
        consumed = False
        async def body():
            nonlocal consumed
            consumed = True
            yield b'private untrusted bytes'
        response = await self.http.put('/api/v1/attachments/unknown/content', content=body())
        self.assertEqual(response.status_code, 401)
        self.assertFalse(consumed)
