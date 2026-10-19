"""Runtime configuration; secret values are never represented in logs."""
from dataclasses import dataclass, field
from pathlib import Path
import os
import re
from urllib.parse import urlsplit


@dataclass(frozen=True, slots=True)
class Settings:
    bot_token: str = field(repr=False)
    admin_id: int
    database_url: str = field(repr=False)
    app_origin: str
    development: bool = False
    owner_username: str = 'DXNIAR'
    s3_endpoint: str = ''
    s3_bucket: str = ''
    s3_access_key: str = field(default='', repr=False)
    s3_secret_key: str = field(default='', repr=False)
    s3_region: str = 'auto'
    s3_addressing_style: str = 'virtual'
    session_seconds: int = 28_800
    init_data_seconds: int = 300
    frontend_dir: Path = Path('web/dist')
    trusted_proxy: str = ''

    def __post_init__(self):
        origin = urlsplit(self.app_origin)
        if not isinstance(self.admin_id, int) or isinstance(self.admin_id, bool) or self.admin_id <= 0:
            raise ValueError('ADMIN_ID должен быть положительным числом.')
        if not self.bot_token or ':' not in self.bot_token:
            raise ValueError('BOT_TOKEN не заполнен.')
        if origin.scheme not in ('http', 'https') or not origin.netloc or origin.username or origin.query or origin.fragment or origin.path not in ('', '/'):
            raise ValueError('APP_ORIGIN должен содержать только протокол и домен.')
        if not self.development and origin.scheme != 'https':
            raise ValueError('Для размещения APP_ORIGIN должен использовать HTTPS.')
        if not self.database_url.startswith(('postgresql://', 'postgresql+psycopg://')):
            if not (self.development and self.database_url.startswith('sqlite+aiosqlite://')):
                raise ValueError('Для сервиса требуется PostgreSQL DATABASE_URL.')
        if self.session_seconds <= 0 or self.init_data_seconds <= 0:
            raise ValueError('Срок сессии должен быть положительным.')
        if self.s3_addressing_style not in ('virtual', 'path'):
            raise ValueError('S3_ADDRESSING_STYLE: virtual или path.')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}', self.owner_username):
            raise ValueError('OWNER_USERNAME должен содержать Telegram username без ссылки.')
        object.__setattr__(self, 'app_origin', self.app_origin.rstrip('/'))

    def require_storage(self):
        if not all((self.s3_endpoint, self.s3_bucket, self.s3_access_key, self.s3_secret_key)):
            raise ValueError('Не настроено приватное S3-хранилище.')
        if urlsplit(self.s3_endpoint).scheme != 'https' and not self.development:
            raise ValueError('S3_ENDPOINT должен использовать HTTPS.')

    @classmethod
    def from_env(cls, *, load_file: bool = False):
        if load_file:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).resolve().parent.parent / '.env', encoding='utf-8-sig')
        try:
            owner = int(os.environ.get('ADMIN_ID', '0'))
        except ValueError:
            raise ValueError('ADMIN_ID должен быть целым числом.') from None
        return cls(
            bot_token=os.environ.get('BOT_TOKEN', '').strip(), admin_id=owner,
            database_url=os.environ.get('DATABASE_URL', ''),
            app_origin=os.environ.get('APP_ORIGIN', ''),
            development=os.environ.get('STUDIO_ENV') == 'development',
            owner_username=os.environ.get('OWNER_USERNAME', 'DXNIAR').removeprefix('@'),
            s3_endpoint=os.environ.get('S3_ENDPOINT', ''), s3_bucket=os.environ.get('S3_BUCKET', ''),
            s3_access_key=os.environ.get('S3_ACCESS_KEY_ID', ''),
            s3_secret_key=os.environ.get('S3_SECRET_ACCESS_KEY', ''),
            s3_region=os.environ.get('S3_REGION', 'auto'),
            s3_addressing_style=os.environ.get('S3_ADDRESSING_STYLE', 'virtual'),
            trusted_proxy=os.environ.get('TRUSTED_PROXY', ''),
        )
