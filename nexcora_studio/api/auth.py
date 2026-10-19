from fastapi import APIRouter, Depends, Header, Request
from ..auth import user_dto
from ..errors import DomainError
from ..models import User
from ..schemas import TelegramLogin
from .dependencies import principal, source_ip

router = APIRouter(prefix='/api/v1')


@router.post('/auth/telegram')
async def login(body: TelegramLogin, request: Request):
    return await request.app.state.auth.login(body.init_data, source_ip(request))


@router.get('/me')
async def me(request: Request, actor=Depends(principal)):
    async with request.app.state.db.session() as session:
        user = await session.get(User, actor.user_id)
        if user is None: raise DomainError('session_expired', 'Откройте приложение заново из Telegram.', 401)
        return user_dto(user, request.app.state.settings.admin_id)


@router.post('/auth/logout')
async def logout(request: Request, actor=Depends(principal), authorization: str = Header()):
    await request.app.state.auth.logout(authorization[7:])
    return {'logged_out': True}
