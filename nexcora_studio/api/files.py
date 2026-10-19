import os
from pathlib import Path
import tempfile
from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import FileResponse
from pydantic import Field
from starlette.background import BackgroundTask
from ..schemas import StrictBody
from .dependencies import idempotency_key, principal

router = APIRouter(prefix='/api/v1')


class ReserveFile(StrictBody):
    filename: str = Field(min_length=1, max_length=1024)
    size_bytes: int = Field(ge=1)
    expected_attachments_version: int = Field(ge=0)


@router.post('/me/draft/attachments')
async def reserve(body: ReserveFile, request: Request, actor=Depends(principal), key: str | None = Header(default=None, alias='Idempotency-Key')):
    return await request.app.state.files.reserve(actor, body.filename, body.size_bytes, body.expected_attachments_version, idempotency_key(key))


@router.put('/attachments/{file_id}/content')
async def upload(file_id: str, request: Request, actor=Depends(principal)):
    return await request.app.state.files.upload(actor, file_id, request.stream(), content_length=request.headers.get('content-length'))


@router.delete('/attachments/{file_id}')
async def delete(file_id: str, request: Request, actor=Depends(principal)):
    return await request.app.state.files.delete(actor, file_id)


@router.get('/attachments/{file_id}/download')
async def download(file_id: str, request: Request, actor=Depends(principal)):
    temporary = tempfile.NamedTemporaryFile(prefix='nexcora-download-', delete=False)
    path = Path(temporary.name)
    temporary.close()
    try:
        metadata = await request.app.state.files.download(actor, file_id, path)
        return FileResponse(path, filename=metadata['filename'], media_type='application/octet-stream',
                            headers={'Cache-Control': 'private, no-store'}, background=BackgroundTask(path.unlink, missing_ok=True))
    except BaseException:
        path.unlink(missing_ok=True)
        raise
