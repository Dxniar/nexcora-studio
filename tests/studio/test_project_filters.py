"""Project filters must constrain scope and totals before the ten-item page."""
from datetime import datetime, timedelta, timezone

import httpx

from nexcora_studio.app import create_app
from nexcora_studio.models import AttachmentGroup, Project
from tests.studio.cases import StudioCase
from tests.studio.fakes import MemoryStorage
from tests.studio.helpers import signed_init


class ProjectFilterTests(StudioCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        app = create_app(self.settings, database=self.db, storage=MemoryStorage())
        self.http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=self.settings.app_origin)

    async def asyncTearDown(self):
        await self.http.aclose()
        await super().asyncTearDown()

    async def headers(self, user_id=101):
        response = await self.http.post('/api/v1/auth/telegram', json={
            'init_data': signed_init(user_id, int(datetime.now(timezone.utc).timestamp())),
        })
        self.assertEqual(response.status_code, 200, response.text)
        return {'Authorization': 'Bearer ' + response.json()['access_token']}

    async def seed_projects(self, rows):
        """Rows are oldest first, independently of insertion IDs or wall time."""
        ids = []
        async with self.db.session() as session:
            for index, row in enumerate(rows):
                user_id = row.get('user_id', 101)
                group = AttachmentGroup(user_id=user_id, phase='submitted')
                session.add(group)
                await session.flush()
                project = Project(
                    user_id=user_id, group_id=group.id, service_id='bot',
                    service_title='Бот', name=row.get('name', 'Проект'),
                    description='Тестовая задача для фильтрации', status=row['status'],
                    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=index),
                )
                session.add(project)
                await session.flush()
                ids.append(project.id)
        return ids

    async def test_active_filter_finds_older_project_beyond_terminal_page_and_excludes_foreign_client(self):
        ids = await self.seed_projects(
            [{'status': 'in_progress'}]
            + [{'status': status} for status in ['completed', 'closed'] * 6]
            + [{'status': 'new', 'user_id': 202}]
        )

        response = await self.http.get('/api/v1/me/projects', params={'active_only': 'true'}, headers=await self.headers())

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['total'], 1)
        self.assertEqual([item['id'] for item in response.json()['items']], [ids[0]])

    async def test_active_filter_counts_and_pages_all_six_active_states(self):
        ids = await self.seed_projects(
            [{'status': status} for status in ['new', 'discussing', 'proposal_sent', 'agreed', 'in_progress', 'review'] * 2]
            + [{'status': status} for status in ['completed', 'closed'] * 6]
            + [{'status': 'review', 'user_id': 202}]
        )
        headers = await self.headers()

        first = await self.http.get('/api/v1/me/projects', params={'active_only': 'true'}, headers=headers)
        second = await self.http.get('/api/v1/me/projects', params={'active_only': 'true', 'offset': 10}, headers=headers)

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual((first.json()['total'], first.json()['offset'], first.json()['limit']), (12, 0, 10))
        self.assertEqual([item['id'] for item in first.json()['items']], [ids[11], ids[10], ids[9], ids[8], ids[7], ids[6], ids[5], ids[4], ids[3], ids[2]])
        self.assertEqual((second.json()['total'], second.json()['offset'], second.json()['limit']), (12, 10, 10))
        self.assertEqual([item['id'] for item in second.json()['items']], [ids[1], ids[0]])

    async def test_client_default_and_false_filter_still_include_terminal_projects(self):
        ids = await self.seed_projects([
            {'status': 'new'}, {'status': 'completed'}, {'status': 'closed'},
            {'status': 'new', 'user_id': 202},
        ])
        headers = await self.headers()

        default = await self.http.get('/api/v1/me/projects', headers=headers)
        explicit_false = await self.http.get('/api/v1/me/projects', params={'active_only': 'false'}, headers=headers)

        self.assertEqual(default.status_code, 200, default.text)
        self.assertEqual(explicit_false.status_code, 200, explicit_false.text)
        self.assertEqual(default.json()['total'], 3)
        self.assertEqual([item['id'] for item in default.json()['items']], [ids[2], ids[1], ids[0]])
        self.assertEqual(default.json(), explicit_false.json())

    async def test_attention_filter_includes_agreed_and_matches_summary_across_clients(self):
        ids = await self.seed_projects([
            {'status': 'new'}, {'status': 'discussing', 'user_id': 202}, {'status': 'agreed'},
            {'status': 'proposal_sent'}, {'status': 'in_progress'}, {'status': 'review'},
            {'status': 'completed'}, {'status': 'closed'},
        ])
        headers = await self.headers(999)

        response = await self.http.get('/api/v1/owner/projects', params={'attention': 'true'}, headers=headers)
        summary = await self.http.get('/api/v1/owner/summary', headers=headers)

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(response.json()['total'], 3)
        self.assertEqual([item['id'] for item in response.json()['items']], [ids[2], ids[1], ids[0]])
        self.assertEqual(summary.json()['needs_response'], 3)

    async def test_attention_filter_counts_before_pagination_past_newer_terminal_projects(self):
        ids = await self.seed_projects(
            [{'status': status} for status in ['new', 'discussing', 'agreed'] * 4]
            + [{'status': status} for status in ['completed', 'closed'] * 6]
        )
        headers = await self.headers(999)

        first = await self.http.get('/api/v1/owner/projects', params={'attention': 'true'}, headers=headers)
        second = await self.http.get('/api/v1/owner/projects', params={'attention': 'true', 'offset': 10}, headers=headers)

        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual((first.json()['total'], first.json()['offset'], first.json()['limit']), (12, 0, 10))
        self.assertEqual([item['id'] for item in first.json()['items']], [ids[11], ids[10], ids[9], ids[8], ids[7], ids[6], ids[5], ids[4], ids[3], ids[2]])
        self.assertEqual((second.json()['total'], second.json()['offset'], second.json()['limit']), (12, 10, 10))
        self.assertEqual([item['id'] for item in second.json()['items']], [ids[1], ids[0]])

    async def test_attention_intersects_status_and_search_filters(self):
        ids = await self.seed_projects([
            {'status': 'new', 'name': 'Needle new'},
            {'status': 'agreed', 'name': 'Needle agreed'},
            {'status': 'discussing', 'name': 'Other project'},
            {'status': 'in_progress', 'name': 'Needle working'},
            {'status': 'agreed', 'name': 'Needle foreign', 'user_id': 202},
            {'status': 'agreed', 'name': 'Other agreed'},
        ])
        headers = await self.headers(999)

        agreed = await self.http.get('/api/v1/owner/projects', params={'attention': 'true', 'status': 'agreed', 'search': 'Needle'}, headers=headers)
        working = await self.http.get('/api/v1/owner/projects', params={'attention': 'true', 'status': 'in_progress', 'search': 'Needle'}, headers=headers)

        self.assertEqual(agreed.status_code, 200, agreed.text)
        self.assertEqual(working.status_code, 200, working.text)
        self.assertEqual(agreed.json()['total'], 2)
        self.assertEqual([item['id'] for item in agreed.json()['items']], [ids[4], ids[1]])
        self.assertEqual(working.json()['total'], 0)
        self.assertEqual(working.json()['items'], [])

    async def test_owner_default_and_false_filter_preserve_the_complete_queue(self):
        ids = await self.seed_projects([
            {'status': 'new', 'user_id': 202}, {'status': 'discussing'}, {'status': 'agreed'},
            {'status': 'proposal_sent'}, {'status': 'in_progress'}, {'status': 'review'},
            {'status': 'completed'}, {'status': 'closed'},
        ])
        headers = await self.headers(999)

        default = await self.http.get('/api/v1/owner/projects', headers=headers)
        explicit_false = await self.http.get('/api/v1/owner/projects', params={'attention': 'false'}, headers=headers)

        self.assertEqual(default.status_code, 200, default.text)
        self.assertEqual(explicit_false.status_code, 200, explicit_false.text)
        self.assertEqual(default.json()['total'], 8)
        self.assertEqual([item['id'] for item in default.json()['items']], [ids[7], ids[6], ids[5], ids[4], ids[3], ids[2], ids[1], ids[0]])
        self.assertEqual(default.json(), explicit_false.json())

    async def test_client_cannot_read_owner_attention_queue(self):
        await self.seed_projects([{'status': 'new', 'user_id': 202}])

        response = await self.http.get('/api/v1/owner/projects', params={'attention': 'true'}, headers=await self.headers())

        self.assertEqual(response.status_code, 403, response.text)
        self.assertEqual(response.json()['error']['code'], 'owner_required')
