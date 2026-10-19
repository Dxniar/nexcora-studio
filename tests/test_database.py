import tempfile
import unittest
from pathlib import Path

from orderbot.database import (
    delete_user_orders,
    get_recent_orders,
    initialize_database,
    save_order,
)


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_create_read_and_delete(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orders.sqlite3"
            await initialize_database(path)
            order_id = await save_order(
                path,
                telegram_user_id=123,
                username="test_user",
                service="Консультация",
                client_name="Айша",
                phone="+77001234567",
                comment="Тестовая заявка",
            )
            self.assertEqual(order_id, 1)
            orders = await get_recent_orders(path)
            self.assertEqual(len(orders), 1)
            self.assertEqual(orders[0]["client_name"], "Айша")
            self.assertEqual(await delete_user_orders(path, 123), 1)
            self.assertEqual(await get_recent_orders(path), [])
