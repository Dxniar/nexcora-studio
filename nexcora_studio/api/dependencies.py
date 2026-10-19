import ipaddress
from fastapi import Header, Request
from ..errors import DomainError


async def principal(request: Request, authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith('Bearer '):
        raise DomainError('authentication_required', 'Откройте приложение из Telegram.', 401)
    return await request.app.state.auth.principal(authorization[7:])


def idempotency_key(value):
    if not value:
        raise DomainError('idempotency_key_required', 'Необходим ключ операции.', 422)
    return value


def source_ip(request):
    peer = request.client.host if request.client else 'unknown'
    trusted = request.app.state.settings.trusted_proxy
    if trusted:
        try:
            if ipaddress.ip_address(peer) in ipaddress.ip_network(trusted):
                forwarded = request.headers.get('x-forwarded-for', '')
                # Accept only a single trusted hop; arbitrary untrusted chains are ignored.
                if forwarded and ',' not in forwarded:
                    return str(ipaddress.ip_address(forwarded.strip()))
        except ValueError:
            pass
    return peer
