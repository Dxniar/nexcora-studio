"""Telegram HMAC validation and revocable opaque database sessions.

Algorithm: https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import json
import re
import secrets
from urllib.parse import parse_qsl
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from .errors import DomainError
from .i18n import normalize_language
from .models import RateLimit, Session, User, utcnow


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


@dataclass(frozen=True, slots=True)
class TelegramIdentity:
    user_id: int
    first_name: str
    username: str | None
    language_code: str = 'ru'


@dataclass(frozen=True, slots=True)
class Principal:
    user_id: int
    is_owner: bool

    def require_owner(self):
        if not self.is_owner:
            raise DomainError('owner_required', 'Доступен только владельцу.', 403)


def verify_init_data(raw: str, bot_token: str, now: datetime, *, max_age: int = 300) -> TelegramIdentity:
    invalid = lambda: DomainError('invalid_telegram_auth', 'Откройте приложение заново из Telegram.', 401)
    try:
        if not isinstance(raw, str) or not 1 <= len(raw.encode('utf-8')) <= 16_384:
            raise invalid()
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True, max_num_fields=64, encoding='utf-8', errors='strict')
        values = dict(pairs)
        if len(pairs) != len(values) or not all(key in values for key in ('hash', 'auth_date', 'user')):
            raise invalid()
        received = values.pop('hash')
        if not re.fullmatch(r'[0-9a-f]{64}', received):
            raise invalid()
        check = '\n'.join(f'{key}={value}' for key, value in sorted(values.items()))
        secret = hmac.digest(b'WebAppData', bot_token.encode('utf-8'), 'sha256')
        expected = hmac.new(secret, check.encode('utf-8'), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(received, expected):
            raise invalid()
        if not re.fullmatch(r'[0-9]{1,12}', values['auth_date']):
            raise invalid()
        age = as_utc(now).timestamp() - int(values['auth_date'])
        if age > max_age or age < -30:
            raise invalid()
        user = json.loads(values['user'])
        user_id = user.get('id')
        if not isinstance(user_id, int) or isinstance(user_id, bool) or not 0 < user_id < 2 ** 63:
            raise invalid()
        name, username = user.get('first_name', ''), user.get('username')
        if not isinstance(name, str) or len(name) > 256 or (username is not None and (not isinstance(username, str) or len(username) > 256)):
            raise invalid()
        return TelegramIdentity(user_id, name, username, normalize_language(user.get('language_code')))
    except DomainError:
        raise
    except (ValueError, TypeError, AttributeError, UnicodeError, OverflowError):
        raise invalid() from None


def user_dto(user: User, owner_id: int) -> dict:
    return {'id': user.id, 'first_name': user.first_name, 'username': user.username,
            'is_owner': user.id == owner_id, 'notifications_enabled': user.notifications_enabled,
            'preference_version': user.preference_version, 'language_code': normalize_language(user.language_code)}


async def upsert_telegram_user(session, dialect_name: str, identity: TelegramIdentity) -> User:
    """Share an account across bot and app without overwriting its saved language."""
    insert = pg_insert if dialect_name == 'postgresql' else sqlite_insert
    statement = insert(User).values(id=identity.user_id, first_name=identity.first_name,
                                    username=identity.username, language_code=normalize_language(identity.language_code))
    await session.execute(statement.on_conflict_do_update(index_elements=['id'],
        set_={'first_name': identity.first_name, 'username': identity.username}))
    return await session.get(User, identity.user_id)


class AuthService:
    def __init__(self, database, settings):
        self.db, self.settings = database, settings

    async def _limit(self, key: str, maximum: int, now: datetime):
        window = int(as_utc(now).timestamp()) // 60
        insert = pg_insert if self.db.engine.dialect.name == 'postgresql' else sqlite_insert
        async with self.db.session() as session:
            statement = insert(RateLimit).values(key=key, window=window, count=1)
            statement = statement.on_conflict_do_update(index_elements=['key', 'window'], set_={'count': RateLimit.count + 1}).returning(RateLimit.count)
            count = await session.scalar(statement)
            await session.execute(delete(RateLimit).where(RateLimit.window < window - 2))
        if count > maximum:
            raise DomainError('auth_rate_limit', 'Слишком много попыток. Повторите через минуту.', 429)

    async def login(self, raw: str, source_ip: str, *, now: datetime | None = None) -> dict:
        now = now or utcnow()
        ip_key = hmac.new(self.settings.bot_token.encode(), source_ip.encode(), hashlib.sha256).hexdigest()
        await self._limit('ip:' + ip_key, 30, now)
        identity = verify_init_data(raw, self.settings.bot_token, now, max_age=self.settings.init_data_seconds)
        await self._limit(f'user:{identity.user_id}', 10, now)
        token = secrets.token_urlsafe(32)
        expires = now + timedelta(seconds=self.settings.session_seconds)
        async with self.db.session() as session:
            user = await upsert_telegram_user(session, self.db.engine.dialect.name, identity)
            session.add(Session(token_hash=token_hash(token), user_id=user.id, expires_at=expires))
            result = user_dto(user, self.settings.admin_id)
        return {'access_token': token, 'expires_at': as_utc(expires).isoformat(), 'user': result}

    async def principal(self, token: str, *, now: datetime | None = None) -> Principal:
        if not isinstance(token, str) or not 20 <= len(token) <= 128:
            raise DomainError('session_expired', 'Откройте приложение заново из Telegram.', 401)
        async with self.db.session() as session:
            record = await session.get(Session, token_hash(token))
            if record is None or as_utc(record.expires_at) <= as_utc(now or utcnow()):
                raise DomainError('session_expired', 'Откройте приложение заново из Telegram.', 401)
            return Principal(record.user_id, record.user_id == self.settings.admin_id)

    async def logout(self, token: str):
        async with self.db.session() as session:
            await session.execute(delete(Session).where(Session.token_hash == token_hash(token)))
