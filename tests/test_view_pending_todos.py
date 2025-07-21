import unittest
from gway import gw

class ViewPendingTodosTests(unittest.TestCase):
    def test_view_renders_todo_table(self):
        gw.help_db.build(update=True)
        html = gw.web.site.view_pending_todos()
        self.assertIn('<table', html)
        self.assertIn('ocpp.rfid', html)
        self.assertNotIn('Function</th>', html)
        self.assertIn('Create TODO Request', html)
        self.assertIn('topic=TODO+Request+%40+ocpp.rfid', html)
        self.assertGreaterEqual(html.count('Create TODO Request'), 1)

if __name__ == '__main__':
    unittest.main()
