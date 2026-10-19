"""Чтение конфигурации из переменных окружения / .env."""
from dataclasses import dataclass
import os
import re
from pathlib import Path

from dotenv import dotenv_values, load_dotenv


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_id: int | None
    db_path: Path
    owner_username: str = "DXNIAR"


def load_config() -> Config:
    env_path = Path(__file__).resolve().parent.parent / '.env'
    load_dotenv(env_path, encoding='utf-8-sig')
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token or token == "put_your_bot_token_here":
        token = (dotenv_values(env_path, encoding='utf-8-sig').get('BOT_TOKEN') or '').strip()
    if not token or token == "put_your_bot_token_here":
        raise ValueError(f"Заполни BOT_TOKEN в файле {env_path}. Получить токен: @BotFather.")

    raw_admin_id = os.getenv("ADMIN_ID", "").strip()
    if raw_admin_id:
        try:
            admin_id = int(raw_admin_id)
        except ValueError as exc:
            raise ValueError("ADMIN_ID должен быть целым числом.") from exc
        if admin_id <= 0:
            raise ValueError("ADMIN_ID должен быть положительным числом.")
    else:
        admin_id = None

    owner_username = os.getenv("OWNER_USERNAME", "DXNIAR").strip().removeprefix("@")
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{4,31}", owner_username):
        raise ValueError("OWNER_USERNAME: укажи Telegram username без ссылки, например DXNIAR.")

    db_path = Path(os.getenv("DB_PATH", "data/orders.sqlite3"))
    return Config(bot_token=token, admin_id=admin_id, db_path=db_path, owner_username=owner_username)
