import os
import unittest
from unittest.mock import patch
import pytest
from gway import gw
from gway.builtins import is_test_flag

pytestmark = pytest.mark.odoo

odoo = gw.load_project("odoo")


@unittest.skipUnless(is_test_flag("odoo"), "Odoo tests disabled")
class TestCreateTask(unittest.TestCase):
    def test_title_defaults_to_customer(self):
        calls = {}
        def fake_execute_kw(args, kwargs, *, model, method):
            if model == 'res.partner' and method == 'create':
                calls['partner'] = args[0]
                return 5
            if model == 'project.task' and method == 'create':
                calls['task'] = args[0]
                return 10
            if model == 'project.task' and method == 'read':
                return [{**calls['task'], 'id': 10}]
            return []

        os.environ.setdefault("ODOO_BASE_URL", "http://example.com")
        os.environ.setdefault("ODOO_DB_NAME", "db")
        os.environ.setdefault("ODOO_ADMIN_USER", "user")
        os.environ.setdefault("ODOO_ADMIN_PASSWORD", "pass")
        with patch('odoo.execute_kw', side_effect=fake_execute_kw):
            task = odoo.create_task(
                project=1,
                customer='ACME',
                phone='123',
                notes='Hello',
                new_customer=True,
            )
        self.assertEqual(task[0]['name'], 'ACME')
        self.assertEqual(calls['task']['name'], 'ACME')
        self.assertEqual(calls['task']['project_id'], 1)
        self.assertEqual(calls['task']['partner_id'], 5)
        self.assertEqual(task[0]['description'], 'Phone: 123\nHello')


@unittest.skipUnless(is_test_flag("odoo"), "Odoo tests disabled")
class TestQuoteTags(unittest.TestCase):
    def test_fetch_quote_tags(self):
        def fake_execute_kw(args, kwargs, *, model, method):
            self.assertEqual(model, 'crm.tag')
            self.assertEqual(method, 'search_read')
            self.assertEqual(kwargs['fields'], ['id', 'name'])
            return [{'id': 1, 'name': 'VIP'}]

        with patch('odoo.execute_kw', side_effect=fake_execute_kw):
            res = odoo.fetch_quote_tags()
        self.assertEqual(res[0]['name'], 'VIP')

    def test_fetch_quotes_with_tag(self):
        captured = {}

        def fake_execute_kw(args, kwargs, *, model, method):
            captured['domain'] = args[0]
            return []

        with patch('odoo.execute_kw', side_effect=fake_execute_kw):
            odoo.fetch_quotes(tag='VIP')
        self.assertIn(('tag_ids.name', 'ilike', 'VIP'), captured['domain'])

    def test_fetch_quotes_with_ws_tag(self):
        captured = {}

        def fake_execute_kw(args, kwargs, *, model, method):
            captured['domain'] = args[0]
            return []

        with patch('odoo.execute_kw', side_effect=fake_execute_kw):
            odoo.fetch_quotes(ws_tag='VIP Customer')
        self.assertIn(('tag_ids.name', 'ilike', 'VIP Customer'), captured['domain'])


@unittest.skipUnless(is_test_flag("odoo"), "Odoo tests disabled")
class TestFindQuotes(unittest.TestCase):
    def test_find_quotes_with_tag(self):
        captured = {}

        def fake_execute_kw(args, kwargs, *, model, method):
            if model == 'sale.order.line':
                return [{
                    'order_id': (42, 'Q00042'),
                    'product_id': 5,
                    'product_uom_qty': 2,
                    'name': 'P1'
                }]
            if model == 'sale.order':
                captured['domain'] = args[0]
                return [{'id': 42}]
            return []

        with patch('odoo.execute_kw', side_effect=fake_execute_kw):
            odoo.find_quotes(product=5, tag='VIP')

        self.assertIn(('tag_ids.name', 'ilike', 'VIP'), captured['domain'])


@unittest.skipUnless(is_test_flag("odoo"), "Odoo tests disabled")
class TestSplitWsTags(unittest.TestCase):
    def test_split_ws_tags(self):
        def fake_fetch_quote_tags(name=None):
            self.assertEqual(name, ' ')
            return [{'id': 1, 'name': 'VIP Customer'}]

        def fake_fetch_quotes(tag=None):
            self.assertEqual(tag, 1)
            return [{'id': 10}]

        ops = {}

        def fake_execute_kw(args, kwargs=None, *, model, method):
            if model == 'crm.tag' and method == 'search_read':
                token = args[0][0][2]
                if token == 'VIP':
                    return [{'id': 2}]
                return []
            if model == 'crm.tag' and method == 'create':
                return 3
            if model == 'sale.order' and method == 'write':
                ops['tag_ids'] = args[0][1]['tag_ids']
                return True
            return []

        with patch('odoo.fetch_quote_tags', side_effect=fake_fetch_quote_tags):
            with patch('odoo.fetch_quotes', side_effect=fake_fetch_quotes):
                with patch('odoo.execute_kw', side_effect=fake_execute_kw):
                    res = odoo.split_ws_quote_tags()

        self.assertEqual(ops['tag_ids'], [(3, 1), (4, 2), (4, 3)])
        self.assertEqual(res, [{'quote': 10, 'removed': 1, 'added': [2, 3]}])


if __name__ == '__main__':
    unittest.main()
