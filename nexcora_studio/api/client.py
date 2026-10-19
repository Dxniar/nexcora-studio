from dataclasses import asdict
from fastapi import APIRouter, Depends, Header, Request
from orderbot.catalog import SERVICES
from ..schemas import Action, DeleteData, LanguagePreference, Preferences, SaveDraft, SubmitDraft
from .dependencies import idempotency_key, principal

router = APIRouter(prefix='/api/v1')


@router.get('/catalog')
async def catalog():
    return {'items': [asdict(service) for service in SERVICES]}


@router.get('/config')
async def config(request: Request):
    settings = request.app.state.settings
    return {'brand': 'Nexcora Studio', 'owner_username': settings.owner_username,
            'file_limits': {'count': 5, 'file_bytes': 10_485_760, 'total_bytes': 52_428_800,
                            'extensions': ['txt', 'pdf', 'doc', 'docx', 'jpg', 'jpeg', 'png', 'webp']}}


@router.get('/me/draft')
async def draft(request: Request, actor=Depends(principal)):
    return await request.app.state.projects.get_draft(actor)


@router.put('/me/draft')
async def save_draft(body: SaveDraft, request: Request, actor=Depends(principal)):
    return await request.app.state.projects.save_draft(actor, body.fields, body.expected_version)


@router.post('/me/draft/submit')
async def submit(body: SubmitDraft, request: Request, actor=Depends(principal), key: str | None = Header(default=None, alias='Idempotency-Key')):
    return await request.app.state.projects.submit(actor, body.draft_id, body.expected_version, body.attachments_version, idempotency_key(key))


@router.get('/me/projects')
async def projects(request: Request, offset: int = 0, active_only: bool = False, actor=Depends(principal)):
    return await request.app.state.projects.list_projects(actor, offset=offset, active_only=active_only)


@router.get('/me/projects/{project_id}')
async def project(project_id: int, request: Request, actor=Depends(principal)):
    return await request.app.state.projects.get_project(actor, project_id)


def register_action(path, name):
    async def perform(project_id: int, body: Action, request: Request, actor=Depends(principal), key: str | None = Header(default=None, alias='Idempotency-Key')):
        return await request.app.state.projects.act(actor, project_id, name, body.model_dump(exclude_none=True), idempotency_key(key))
    router.add_api_route('/me/projects/{project_id}/' + path, perform, methods=['POST'], name=name)


for path, name in [('accept-proposal', 'accept_proposal'), ('request-changes', 'request_changes'), ('accept-delivery', 'accept_delivery'), ('request-revision', 'request_revision')]:
    register_action(path, name)


@router.put('/me/preferences')
async def preferences(body: Preferences, request: Request, actor=Depends(principal)):
    return await request.app.state.privacy.set_preferences(actor, body.notifications_enabled, body.expected_version)


@router.put('/me/language')
async def language(body: LanguagePreference, request: Request, actor=Depends(principal)):
    return await request.app.state.privacy.set_language(actor, body.language_code)


@router.post('/me/deletion-confirmation')
async def confirm_deletion(request: Request, actor=Depends(principal)):
    return await request.app.state.privacy.confirm_deletion(actor)


@router.delete('/me/data')
async def delete_data(body: DeleteData, request: Request, actor=Depends(principal)):
    return await request.app.state.privacy.delete_data(actor, body.confirmation_token)
