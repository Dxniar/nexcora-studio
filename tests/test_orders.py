from repo_helpers import RepoCase
from orderbot.models import AccessDenied, Conflict, InvalidInput


class OrderTests(RepoCase):
    async def test_lists_permissions_and_pages(self):
        ids = []
        for _ in range(7):
            ids.append((await self.submitted()).order['id'])
            self.clock.value += 31
        await self.submitted(456)
        first = await self.repo.list_user_orders(123)
        second = await self.repo.list_user_orders(123, page=1)
        self.assertEqual([len(first.items), len(second.items), first.total], [5,2,7])
        self.assertEqual([r['id'] for r in first.items], list(reversed(ids))[:5])
        self.assertEqual((await self.repo.list_user_orders(123,page=-1)).items, first.items)
        self.assertEqual((await self.repo.list_user_orders(123,page=99)).items, [])
        self.assertIsNone(await self.repo.get_user_order(456, ids[0]))
        with self.assertRaises(AccessDenied): await self.repo.list_admin_orders(456,999)

    async def test_status_transaction_versions_and_opt_out(self):
        order = (await self.submitted()).order
        with self.assertRaises(InvalidInput):
            await self.repo.change_status(999,999,order['id'],0,'completed')
        current = await self.repo.change_status(999,999,order['id'],0,'in_progress')
        with self.assertRaises(Conflict):
            await self.repo.change_status(999,999,order['id'],0,'closed')
        repeated = await self.repo.change_status(999,999,order['id'],1,'in_progress')
        self.assertEqual(repeated['status_version'],1)
        self.assertEqual(len(self.query('SELECT * FROM notification_outbox')),2)
        revision = await self.repo.get_user_revision(123)
        await self.repo.set_notifications_enabled(123,False,expected_revision=revision)
        with self.assertRaises(Conflict):
            await self.repo.set_notifications_enabled(123,True,expected_revision=revision)
        current = await self.repo.change_status(999,999,order['id'],1,'completed')
        current = await self.repo.change_status(999,999,order['id'],2,'discussing')
        self.assertEqual(current['status'],'discussing')
        self.assertEqual(self.query("SELECT state FROM notification_outbox WHERE kind='status_changed'")[0]['state'],'skipped')

    async def test_confirmed_delete_is_atomic_scoped_and_versioned(self):
        await self.submitted()
        await self.submitted(456)
        token = await self.repo.prepare_delete(123)
        await self.completed_draft(123)
        with self.assertRaises(Conflict): await self.repo.delete_user_data(123,token)
        token = await self.repo.prepare_delete(123)
        with self.assertRaises(Conflict): await self.repo.delete_user_data(456,token)
        result = await self.repo.delete_user_data(123,token)
        self.assertEqual([result.orders,result.drafts,result.notifications],[1,1,1])
        self.assertEqual({r['telegram_user_id'] for r in self.query('SELECT * FROM orders')},{456})
        self.assertEqual({r['recipient_id'] for r in self.query('SELECT * FROM notification_outbox')},{999})
        self.assertIsNone(await self.repo.get_draft(123))
        self.assertEqual(self.query('SELECT * FROM user_preferences WHERE user_id=123'),[])

    async def test_expired_and_cancelled_delete(self):
        await self.submitted()
        token = await self.repo.prepare_delete(123)
        self.clock.value += 301
        with self.assertRaises(Conflict): await self.repo.delete_user_data(123,token)
        token = await self.repo.prepare_delete(123)
        await self.repo.cancel_delete(123,token)
        with self.assertRaises(Conflict): await self.repo.delete_user_data(123,token)
        self.assertEqual(len(self.query('SELECT * FROM orders')),1)
