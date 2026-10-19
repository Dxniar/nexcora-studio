"""Facade used by transports; queries enforce client/owner scope explicitly."""
from sqlalchemy import func, or_, select
from ..errors import DomainError, not_found
from ..models import Project
from .common import PortalBase, STATUS_LABELS, integer
from .drafts import DraftOperations
from .workflow import WorkflowOperations


class ProjectService(DraftOperations, WorkflowOperations, PortalBase):
    async def get_project(self, principal, project_id, *, owner=False):
        integer(project_id, 'project_id', minimum=1, maximum=2**63 - 1)
        if owner: self._require_owner(principal)
        async with self.db.session() as session:
            query = select(Project).where(Project.id == project_id)
            if not owner: query = query.where(Project.user_id == principal.user_id)
            project = await session.scalar(query)
            if not project: raise not_found()
            return await self._project_dto(session, project, owner=owner)

    async def list_projects(self, principal, *, owner=False, status=None, search='', offset=0, active_only: bool = False, attention: bool = False):
        if owner: self._require_owner(principal)
        integer(offset, 'offset', maximum=1_000_000)
        if status and status not in STATUS_LABELS: raise DomainError('invalid_status', 'Неизвестный этап.', 422)
        if not isinstance(search, str) or len(search) > 100: raise DomainError('invalid_search', 'Слишком длинный поиск.', 422)
        conditions = [] if owner else [Project.user_id == principal.user_id]
        if active_only: conditions.append(Project.status.not_in(('completed', 'closed')))
        if attention: conditions.append(Project.status.in_(('new', 'discussing', 'agreed')))
        if status: conditions.append(Project.status == status)
        if search.strip():
            value = search.strip().removeprefix('#')
            pattern = '%' + value.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
            conditions.append(or_(Project.id == int(value) if value.isascii() and value.isdigit() and len(value) < 19 else False, Project.name.ilike(pattern, escape='\\')))
        async with self.db.session() as session:
            total = await session.scalar(select(func.count()).select_from(Project).where(*conditions))
            items = (await session.scalars(select(Project).where(*conditions).order_by(Project.created_at.desc(), Project.id.desc()).offset(offset).limit(10))).all()
            return {'items': [await self._project_dto(session, item, owner=owner, detail=False) for item in items], 'total': total, 'offset': offset, 'limit': 10}

    async def summary(self, principal):
        self._require_owner(principal)
        async with self.db.session() as session:
            rows = (await session.execute(select(Project.status, func.count()).group_by(Project.status))).all()
            counts = {status: 0 for status in STATUS_LABELS}
            counts.update(dict(rows))
            return {'total': sum(counts.values()), 'counts': counts,
                    'needs_response': counts['new'] + counts['discussing'] + counts['agreed'],
                    'waiting_client': counts['proposal_sent'], 'in_progress': counts['in_progress'], 'review': counts['review']}
