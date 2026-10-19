import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from orderbot import validation
from orderbot.config import load_config
from orderbot.database import initialize_database, save_order, get_recent_orders, delete_user_orders


class InputTests(unittest.TestCase):
    def test_name_boundaries(self):
        self.assertEqual(validation.clean_name("А" * 80), "А" * 80)
        self.assertIsNone(validation.clean_name("А" * 81))
        self.assertIsNone(validation.clean_name(None))
        self.assertIsNone(validation.clean_name("   "))

    def test_description_boundaries(self):
        self.assertTrue(hasattr(validation, "clean_description"))
        clean = validation.clean_description
        for size in (10, 2000):
            self.assertEqual(clean("  " + "а" * size + "  "), "а" * size)
        for value in (None, "  ", "a" * 9, "a" * 2001):
            self.assertIsNone(clean(value))

    def test_owner_config(self):
        with patch.dict(os.environ, {"BOT_TOKEN": "123:test", "ADMIN_ID": "", "OWNER_USERNAME": "@DXNIAR"}, clear=True):
            config = load_config()
            self.assertEqual(getattr(config, "owner_username", None), "DXNIAR")
        with patch.dict(os.environ, {"BOT_TOKEN": "123:test"}, clear=True):
            self.assertEqual(load_config().owner_username, "DXNIAR")
        for value in ("", "bad/link", "<script>"):
            with patch.dict(os.environ, {"BOT_TOKEN": "123:test", "OWNER_USERNAME": value}, clear=True):
                with self.assertRaises(ValueError):
                    load_config()


class TelegramDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_preserve_old_and_save_without_phone(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "orders.sqlite3"
            await initialize_database(path)
            await save_order(path, telegram_user_id=123, username="old_user", service="old", client_name="Old", phone="+77001234567", comment="old data")
            await initialize_database(path)
            old = (await get_recent_orders(path))[0]
            self.assertEqual(old["phone"], "+77001234567")
            await save_order(path, telegram_user_id=456, username=None, service="Парсер", client_name="Айша", comment="Описание задачи")
            rows = await get_recent_orders(path)
            self.assertEqual(rows[0]["phone"], "")
            self.assertEqual(rows[0]["telegram_user_id"], 456)
            self.assertIsNone(rows[0]["username"])
            self.assertEqual(await delete_user_orders(path, 123), 1)
            self.assertEqual(len(await get_recent_orders(path)), 1)
