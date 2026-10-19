"""Read-only, all-or-nothing transfer from a stopped legacy SQLite snapshot."""
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from orderbot.catalog import SERVICES
from .db import Database
from .models import AttachmentGroup, Draft, Outbox, Project, User, new_id


def _date(raw):
    try:
        value = datetime.fromisoformat(str(raw))
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    except (ValueError, OverflowError):
        raise ValueError('Некорректная историческая дата. Импорт отменён.') from None


def _snapshot(path: Path):
    path = path.resolve(strict=True)
    wal = Path(str(path) + '-wal')
    if wal.exists() and wal.stat().st_size:
        raise ValueError('Для импорта нужна согласованная SQLite backup-копия без активного WAL.')
    with closing(sqlite3.connect(path.as_uri() + '?mode=ro&immutable=1', uri=True)) as source:
        source.row_factory = sqlite3.Row
        version = source.execute('PRAGMA user_version').fetchone()[0]
        if version > 2:
            raise ValueError('Исходная схема новее поддерживаемой версии 2.')
        tables = {row[0] for row in source.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'orders' not in tables:
            raise ValueError('Исходная база не содержит orders.')
        return {name: [dict(row) for row in source.execute(f'SELECT * FROM "{name}"')]
                for name in ('orders', 'drafts', 'user_preferences', 'notification_outbox') if name in tables}


async def import_legacy(source_path, target_url: str, dry_run: bool = True) -> dict:
    rows = _snapshot(Path(source_path))
    users, projects, drafts, groups, outbox = {}, [], [], [], []

    def ensure_user(user_id, name='', username=None):
        if not isinstance(user_id, int) or not 0 < user_id < 2 ** 63:
            raise ValueError('Некорректный исторический Telegram ID.')
        if user_id not in users:
            users[user_id] = User(id=user_id, first_name=str(name)[:256], username=username)
        return users[user_id]

    titles = {service.title: service.id for service in SERVICES}
    for row in rows['orders']:
        ensure_user(row['telegram_user_id'], row['client_name'], row['username'])
        group = AttachmentGroup(id=new_id(), user_id=row['telegram_user_id'], phase='submitted')
        groups.append(group)
        projects.append(Project(
            id=row['id'], user_id=row['telegram_user_id'], draft_id=row.get('draft_id'), group_id=group.id,
            service_id=titles.get(row['service']), service_title=row['service'], name=row['client_name'],
            description=row['comment'], phone=row['phone'], legacy_username=row['username'],
            budget=row.get('budget', ''), deadline=row.get('deadline', ''),
            status=row.get('status', 'new'), version=row.get('status_version', 0), workflow='legacy',
            created_at=_date(row['created_at']), updated_at=_date(row['created_at']),
        ))
    for row in rows.get('drafts', []):
        ensure_user(row['user_id'], row.get('name', ''))
        group = AttachmentGroup(id=new_id(), user_id=row['user_id'])
        groups.append(group)
        drafts.append(Draft(id=row['id'], user_id=row['user_id'], group_id=group.id, version=row.get('revision', 0),
                            fields={key: row.get(key, '') for key in ('service_id', 'description', 'name', 'budget', 'deadline')},
                            legacy_step=row.get('step', 'service'), legacy_return_to_confirm=bool(row.get('return_to_confirm', False)),
                            updated_at=datetime.fromtimestamp(row['updated_at'], timezone.utc)))
    for row in rows.get('user_preferences', []):
        user = ensure_user(row['user_id'])
        user.notifications_enabled = bool(row['notifications_enabled'])
        user.data_version = row.get('data_revision', 0)
        # Old plaintext deletion tokens are intentionally invalidated at the boundary.
    project_by_id = {project.id: project for project in projects}
    for row in rows.get('notification_outbox', []):
        project = project_by_id.get(row['order_id'])
        if project is None:
            raise ValueError('Историческое уведомление ссылается на отсутствующую заявку.')
        outbox.append(Outbox(
            id=row['id'], project_id=project.id, kind=row['kind'], recipient_id=row['recipient_id'],
            recipient_role='owner' if row['kind'] == 'new_order' else 'client',
            project_version=row.get('status_version') or project.version,
            state=row['state'], attempts=row['attempts'], next_attempt_at=datetime.fromtimestamp(row['next_attempt_at'], timezone.utc),
            message_id=row.get('message_id'), error_code=row.get('error_code'),
            legacy_event_key=row['event_key'],
            legacy_metadata={'status_value': row.get('status_value'), 'status_version': row.get('status_version'), 'automatic_delivery': False},
        ))
    report = {'users': len(users), 'projects': len(projects), 'drafts': len(drafts), 'outbox': len(outbox), 'dry_run': dry_run}
    database = Database(target_url)
    try:
        async with database.session() as session:
            if await session.scalar(select(func.count()).select_from(User)) or await session.scalar(select(func.count()).select_from(Project)):
                raise ValueError('Целевая база не пустая. Импорт отменён.')
            if dry_run:
                return report
            session.add_all(users.values())
            await session.flush()
            session.add_all(groups)
            await session.flush()
            session.add_all(projects)
            session.add_all(drafts)
            await session.flush()
            session.add_all(outbox)
            await session.flush()
            for model, expected in ((User, len(users)), (Project, len(projects)), (Draft, len(drafts)), (Outbox, len(outbox))):
                if await session.scalar(select(func.count()).select_from(model)) != expected:
                    raise ValueError('Проверка числа записей не пройдена. Импорт отменён.')
            if database.engine.dialect.name == 'postgresql':
                for table in ('studio_projects', 'studio_outbox'):
                    await session.execute(text(f"SELECT setval(pg_get_serial_sequence('{table}','id'), COALESCE(MAX(id),1), MAX(id) IS NOT NULL) FROM {table}"))
        return report
    except SQLAlchemyError:
        raise ValueError('Импорт отменён из-за ошибки целевой базы; исходник не изменён. Проверьте схему и ограничения.') from None
    finally:
        await database.close()
