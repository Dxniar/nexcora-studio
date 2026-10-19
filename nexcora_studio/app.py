"""Same-origin web/API application; no unauthenticated development login."""
from contextlib import asynccontextmanager
import logging
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException
from .api import auth, client, owner, files, notifications
from .auth import AuthService
from .db import Database
from .errors import DomainError
from .http_security import SecurityMiddleware, error_response
from .services.projects import ProjectService
from .services.privacy import PrivacyService
from .services.attachments import AttachmentService
from .outbox import OutboxService
from .settings import Settings

logger = logging.getLogger('nexcora_studio')


def create_app(settings: Settings | None = None, *, database=None, storage=None):
    settings = settings or Settings.from_env()
    if not settings.development: settings.require_storage()
    if storage is None and settings.s3_bucket:
        from .storage import S3Storage
        storage = S3Storage(settings)
    owns_database = database is None
    database = database or Database(settings.database_url)

    @asynccontextmanager
    async def lifespan(app):
        try:
            yield
        finally:
            if owns_database: await database.close()

    app = FastAPI(title='Nexcora Studio', version='0.1.0', lifespan=lifespan, docs_url='/api/docs' if settings.development else None, redoc_url=None, openapi_url='/api/openapi.json' if settings.development else None)
    app.state.settings, app.state.db, app.state.storage = settings, database, storage
    app.state.auth = AuthService(database, settings)
    app.state.projects = ProjectService(database, settings)
    app.state.privacy = PrivacyService(database, settings)
    app.state.files = AttachmentService(database, settings, storage)
    app.state.notifications = OutboxService(database, settings)
    app.add_middleware(SecurityMiddleware, origin=settings.app_origin)

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc):
        return error_response(exc.code, exc.message, exc.status, request.state.request_id, exc.details)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc):
        return error_response('invalid_input', 'Проверьте заполненные поля.', 422, request.state.request_id)

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc):
        return error_response('not_found' if exc.status_code == 404 else 'request_rejected', 'Запись не найдена.' if exc.status_code == 404 else 'Запрос отклонён.', exc.status_code, request.state.request_id)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request: Request, exc):
        logger.error('Database request failed request_id=%s type=%s', request.state.request_id, type(exc).__name__)
        return error_response('service_unavailable', 'Сервис временно недоступен. Повторите позже.', 503, request.state.request_id)

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc):
        logger.error('Request failed request_id=%s type=%s', request.state.request_id, type(exc).__name__)
        return error_response('internal_error', 'Не удалось выполнить действие. Повторите позже.', 500, request.state.request_id)

    @app.get('/health/live')
    async def live():
        return {'status': 'alive'}

    @app.get('/health/ready')
    async def ready(request: Request):
        try:
            async with database.session() as session:
                await session.execute(text('SELECT 1 FROM studio_projects LIMIT 1'))
        except SQLAlchemyError:
            return error_response('not_ready', 'Сервис запускается.', 503, request.state.request_id)
        if app.state.storage is None:
            return error_response('not_ready', 'Хранилище не настроено.', 503, request.state.request_id)
        return {'status': 'ready'}

    app.include_router(auth.router)
    app.include_router(client.router)
    app.include_router(owner.router)
    app.include_router(files.router)
    app.include_router(notifications.router)
    frontend = Path(settings.frontend_dir).resolve()
    if (frontend / 'assets').is_dir():
        app.mount('/assets', StaticFiles(directory=frontend / 'assets'), name='assets')

    @app.get('/{path:path}')
    async def frontend_page(path: str):
        if path.startswith(('api/', 'health/')) or not (frontend / 'index.html').is_file():
            raise HTTPException(404)
        return FileResponse(frontend / 'index.html', media_type='text/html')

    return app
