"""No work starts or completes against unaccepted or obsolete conditions."""
from datetime import date, timedelta
from dataclasses import replace
from nexcora_studio.errors import DomainError
from nexcora_studio.services.projects import ProjectService
from tests.studio.cases import StudioCase


class WorkflowTests(StudioCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.service = ProjectService(self.db, self.settings)
        draft = await self.service.get_draft(self.client)
        draft = await self.service.save_draft(self.client, {'service_id': 'bot', 'description': 'Бот для приёма обращений', 'name': 'Алия'}, draft['version'])
        self.project = await self.service.submit(self.client, draft['id'], draft['version'], 0, 'submit')
        self.terms = {'scope': 'Каталог, анкета и уведомления', 'result': 'Рабочий Telegram-бот и инструкция', 'price_minor': 1500000, 'currency': 'KZT', 'deadline': (date.today() + timedelta(days=14)).isoformat(), 'revision_terms': 'Один раунд правок в рамках согласованного объёма'}

    async def action(self, who, kind, **data):
        payload = {'expected_version': self.project['version'], **data}
        result = await self.service.act(who, self.project['id'], kind, payload, f'{kind}-{self.project["version"]}', owner=who.is_owner)
        self.project = result
        return result

    async def test_full_journey_revision_then_acceptance_has_immutable_history(self):
        with self.assertRaises(DomainError):
            await self.action(self.owner, 'start')
        proposal = await self.action(self.owner, 'publish_proposal', **self.terms)
        self.assertEqual(proposal['status'], 'proposal_sent')
        await self.action(self.client, 'accept_proposal', proposal_version=1)
        await self.action(self.owner, 'start')
        await self.action(self.owner, 'deliver', description='Готовая версия и инструкция', url='https://example.test/result')
        await self.action(self.client, 'request_revision', delivery_version=1, comment='Изменить подпись кнопки')
        await self.action(self.owner, 'deliver', description='Подпись кнопки изменена', url='https://example.test/result-v2')
        result = await self.action(self.client, 'accept_delivery', delivery_version=2)
        self.assertEqual(result['status'], 'completed')
        self.assertEqual(result['accepted_proposal']['price_minor'], 1500000)
        self.assertEqual(len(result['history']), 8)
        self.assertEqual(result['history'][0]['kind'], 'submitted')

    async def test_replacement_proposal_cannot_be_accepted_by_stale_tab(self):
        first = await self.action(self.owner, 'publish_proposal', **self.terms)
        await self.action(self.owner, 'publish_proposal', **(self.terms | {'price_minor': 1700000}))
        with self.assertRaises(DomainError) as caught:
            await self.service.act(self.client, self.project['id'], 'accept_proposal', {'expected_version': first['version'], 'proposal_version': 1}, 'stale', owner=False)
        self.assertEqual(caught.exception.status, 409)
        detail = await self.service.get_project(self.client, self.project['id'])
        self.assertEqual(detail['proposal']['version'], 2)
        self.assertEqual(detail['proposals'][0]['price_minor'], 1500000)

    async def test_client_cannot_publish_or_enter_owner_routes(self):
        with self.assertRaises(DomainError) as caught:
            await self.service.act(self.client, self.project['id'], 'publish_proposal', {'expected_version': 0, **self.terms}, 'forged', owner=True)
        self.assertEqual(caught.exception.status, 403)
        with self.assertRaises(DomainError):
            await self.action(self.client, 'start')

    async def test_rotated_owner_cannot_reuse_a_previously_trusted_principal(self):
        rotated = ProjectService(self.db, replace(self.settings, admin_id=202))
        with self.assertRaises(DomainError) as caught:
            await rotated.summary(self.owner)
        self.assertEqual(caught.exception.status, 403)
        with self.assertRaises(DomainError):
            await rotated.act(self.owner, self.project['id'], 'discuss', {'expected_version': 0}, 'old-owner', owner=True)
