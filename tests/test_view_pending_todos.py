import unittest
from gway import gw

class ViewPendingTodosTests(unittest.TestCase):
    def test_view_renders_todo_table(self):
        gw.help_db.build(update=True)
        html = gw.web.site.view_pending_todos()
        self.assertIn('<table', html)
        self.assertIn('ocpp.rfid', html)
        self.assertIn('Request TODO', html)
        self.assertIn('?topic=TODO+request', html)
        self.assertEqual(html.count('Request TODO'), 1)

if __name__ == '__main__':
    unittest.main()
