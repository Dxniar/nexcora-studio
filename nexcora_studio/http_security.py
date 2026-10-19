"""Bound JSON requests before parsing; do not buffer raw attachment streams."""
import asyncio
import re
from uuid import uuid4
from starlette.responses import JSONResponse

CSP = "default-src 'self'; script-src 'self' https://telegram.org; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors https://web.telegram.org https://*.telegram.org https://*.t.me"


def error_response(code, message, status, request_id, details=None):
    error = {'code': code, 'message': message, 'request_id': request_id}
    if details is not None: error['details'] = details
    return JSONResponse({'error': error}, status_code=status)


class SecurityMiddleware:
    def __init__(self, app, origin):
        self.app, self.origin = app, origin

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            await self.app(scope, receive, send)
            return
        request_id = uuid4().hex
        scope.setdefault('state', {})['request_id'] = request_id
        async def secure_send(message):
            if message['type'] == 'http.response.start':
                headers = list(message.get('headers', []))
                headers += [(b'x-request-id', request_id.encode()), (b'x-content-type-options', b'nosniff'),
                            (b'referrer-policy', b'no-referrer'), (b'content-security-policy', CSP.encode())]
                if scope['path'].startswith('/api/'):
                    headers.append((b'cache-control', b'no-store'))
                message = {**message, 'headers': headers}
            await send(message)
        if scope['method'] in ('POST', 'PUT', 'PATCH', 'DELETE'):
            origins = [value.decode('latin1') for key, value in scope['headers'] if key.lower() == b'origin']
            if origins and (len(origins) != 1 or origins[0] != self.origin):
                await error_response('origin_forbidden', 'Запрос с другого сайта отклонён.', 403, request_id)(scope, receive, secure_send)
                return
            raw_upload = scope['method'] == 'PUT' and re.fullmatch(r'/api/v1/attachments/[^/]{1,64}/content', scope['path'])
            if not raw_upload:
                messages, total = [], 0
                try:
                    async with asyncio.timeout(10):
                        while True:
                            message = await receive()
                            if message['type'] == 'http.disconnect': return
                            total += len(message.get('body', b''))
                            if total > 65_536:
                                await error_response('body_too_large', 'Запрос превышает допустимый размер.', 413, request_id)(scope, receive, secure_send)
                                return
                            messages.append(message)
                            if not message.get('more_body', False): break
                except TimeoutError:
                    await error_response('request_timeout', 'Передача запроса заняла слишком много времени.', 408, request_id)(scope, receive, secure_send)
                    return
                original_receive = receive
                async def replay_receive():
                    return messages.pop(0) if messages else await original_receive()
                receive = replay_receive
        await self.app(scope, receive, secure_send)
