"""Переходы анкеты. SQLite является источником её состояния."""
from dataclasses import replace
from uuid import uuid4
from .catalog import SERVICES, get_service
from .models import Draft, Conflict, InvalidInput, NotFound
from .validation import clean_name, clean_description

STEPS = ('service', 'description', 'budget', 'deadline', 'name', 'confirm')


class DraftService:
    def __init__(self, repo):
        self.repo = repo

    async def start(self, user_id, service_id=None, *, replace=None):
        if service_id is not None and not get_service(service_id):
            raise InvalidInput()
        draft = Draft(uuid4().hex, user_id, service_id=service_id,
                      step='description' if service_id else 'service')
        return await self.repo.create_draft(draft, replace=replace)

    async def current(self, user_id, draft_id, revision):
        draft = await self.repo.get_draft(user_id)
        if not draft or draft.id != draft_id:
            raise NotFound()
        if draft.revision != revision:
            raise Conflict()
        return draft

    async def accept(self, user_id, draft_id, revision, text):
        draft = await self.current(user_id, draft_id, revision)
        field = draft.step
        if field == 'service':
            item = next((s for s in SERVICES if text in (s.id, s.title)), None)
            value = item.id if item else None
        elif field == 'description': value = clean_description(text)
        elif field == 'name': value = clean_name(text)
        elif field in ('budget', 'deadline'):
            value = ' '.join(text.split()) if text else None
            if not value or len(value) > 80: value = None
        else: raise InvalidInput()
        if value is None: raise InvalidInput()
        next_step = 'confirm' if draft.return_to_confirm else STEPS[STEPS.index(field)+1]
        updated = replace(draft, **{'service_id' if field == 'service' else field: value},
                          step=next_step, return_to_confirm=False)
        return await self.repo.update_draft(updated, expected_revision=revision)

    async def skip(self, user_id, draft_id, revision):
        draft = await self.current(user_id, draft_id, revision)
        if draft.step not in ('budget', 'deadline'): raise InvalidInput()
        updated = replace(draft, **{draft.step: ''}, return_to_confirm=False,
                          step='confirm' if draft.return_to_confirm else STEPS[STEPS.index(draft.step)+1])
        return await self.repo.update_draft(updated, expected_revision=revision)

    async def back(self, user_id, draft_id, revision):
        draft = await self.current(user_id, draft_id, revision)
        step = 'confirm' if draft.return_to_confirm else STEPS[max(0, STEPS.index(draft.step)-1)]
        return await self.repo.update_draft(replace(draft, step=step, return_to_confirm=False), expected_revision=revision)

    async def edit(self, user_id, draft_id, revision, field):
        draft = await self.current(user_id, draft_id, revision)
        if draft.step != 'confirm' or field not in STEPS[:-1]: raise InvalidInput()
        return await self.repo.update_draft(replace(draft, step=field, return_to_confirm=True), expected_revision=revision)

    async def submit(self, user_id, draft_id, revision, *, username, admin_id):
        return await self.repo.submit_draft(user_id, draft_id, revision,
                                           username=username, admin_id=admin_id)
