import unittest
from unittest.mock import patch
from gway import gw

odoo = gw.load_project("odoo")


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

        env = {
            'ODOO_BASE_URL': 'http://example.com',
            'ODOO_DB_NAME': 'testdb',
            'ODOO_ADMIN_USER': 'user',
            'ODOO_ADMIN_PASSWORD': 'pass',
        }

        with patch.dict('os.environ', env, clear=False):
            import sys
            mod = sys.modules['odoo']
            original = mod.execute_kw
            mod.execute_kw = fake_execute_kw
            try:
                task = odoo.create_task(
                    project=1,
                    customer='ACME',
                    phone='123',
                    notes='Hello',
                    new_customer=True,
                )
            finally:
                mod.execute_kw = original
        self.assertEqual(task[0]['name'], 'ACME')
        self.assertEqual(calls['task']['name'], 'ACME')
        self.assertEqual(calls['task']['project_id'], 1)
        self.assertEqual(calls['task']['partner_id'], 5)
        self.assertEqual(task[0]['description'], 'Phone: 123\nHello')


if __name__ == '__main__':
    unittest.main()
