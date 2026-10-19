from fastapi import APIRouter, Depends, Request
from .dependencies import principal

router = APIRouter(prefix='/api/v1/owner')


@router.get('/notifications')
async def notifications(request: Request, offset: int = 0, actor=Depends(principal)):
    return await request.app.state.notifications.list_failed(actor, offset=offset)


@router.post('/notifications/{notification_id}/retry')
async def retry_notification(notification_id: int, request: Request, actor=Depends(principal)):
    return await request.app.state.notifications.retry(actor, notification_id)
