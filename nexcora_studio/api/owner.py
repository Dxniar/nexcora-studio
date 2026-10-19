from fastapi import APIRouter, Depends, Header, Request
from ..schemas import Action
from .dependencies import idempotency_key, principal

router = APIRouter(prefix='/api/v1/owner')


@router.get('/summary')
async def summary(request: Request, actor=Depends(principal)):
    return await request.app.state.projects.summary(actor)


@router.get('/projects')
async def projects(request: Request, offset: int = 0, status: str | None = None, search: str = '', attention: bool = False, actor=Depends(principal)):
    return await request.app.state.projects.list_projects(actor, owner=True, offset=offset, status=status, search=search, attention=attention)


@router.get('/projects/{project_id}')
async def project(project_id: int, request: Request, actor=Depends(principal)):
    return await request.app.state.projects.get_project(actor, project_id, owner=True)


def register_action(path, name):
    async def perform(project_id: int, body: Action, request: Request, actor=Depends(principal), key: str | None = Header(default=None, alias='Idempotency-Key')):
        return await request.app.state.projects.act(actor, project_id, name, body.model_dump(exclude_none=True), idempotency_key(key), owner=True)
    router.add_api_route('/projects/{project_id}/' + path, perform, methods=['POST'], name='owner_' + name)


for path, name in [('discuss', 'discuss'), ('proposals', 'publish_proposal'), ('start', 'start'), ('updates', 'update'), ('deliver', 'deliver'), ('close', 'close')]:
    register_action(path, name)
