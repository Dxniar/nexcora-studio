"""Асинхронные обёртки над стандартным sqlite3 через asyncio.to_thread."""
import asyncio
from contextlib import closing
from pathlib import Path
import sqlite3


def _initialize_database(path: Path) -> None:
    from .migrations import initialize
    initialize(path)


async def initialize_database(path: Path) -> None:
    await asyncio.to_thread(_initialize_database, path)


def _save_order(
    path: Path,
    telegram_user_id: int,
    username: str | None,
    service: str,
    client_name: str,
    phone: str,
    comment: str,
) -> int:
    with closing(sqlite3.connect(path, timeout=10)) as db:
        with db:
            cursor = db.execute(
                """INSERT INTO orders
                   (telegram_user_id, username, service, client_name, phone, comment)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (telegram_user_id, username, service, client_name, phone, comment),
            )
            return int(cursor.lastrowid)


async def save_order(
    path: Path,
    *,
    telegram_user_id: int,
    username: str | None,
    service: str,
    client_name: str,
    phone: str = "",
    comment: str,
) -> int:
    return await asyncio.to_thread(
        _save_order, path, telegram_user_id, username, service, client_name, phone, comment
    )


def _get_recent_orders(path: Path, limit: int) -> list[dict]:
    with closing(sqlite3.connect(path, timeout=10)) as db:
        db.row_factory = sqlite3.Row
        rows = db.execute(
            """SELECT *
               FROM orders ORDER BY id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


async def get_recent_orders(path: Path, limit: int = 5) -> list[dict]:
    return await asyncio.to_thread(_get_recent_orders, path, limit)


def _delete_user_orders(path: Path, telegram_user_id: int) -> int:
    with closing(sqlite3.connect(path, timeout=10)) as db:
        db.execute('PRAGMA foreign_keys=ON')
        with db:
            cursor = db.execute(
                "DELETE FROM orders WHERE telegram_user_id = ?", (telegram_user_id,)
            )
            return cursor.rowcount


async def delete_user_orders(path: Path, telegram_user_id: int) -> int:
    return await asyncio.to_thread(_delete_user_orders, path, telegram_user_id)
