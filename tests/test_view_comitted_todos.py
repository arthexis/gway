import unittest
from gway import gw

class ViewComittedTodosTests(unittest.TestCase):
    def test_view_renders_todo_table(self):
        gw.help_db.build(update=True)
        html = gw.web.site.view_comitted_todos()
        self.assertIn('<table', html)
        self.assertIn('ocpp.rfid', html)
        self.assertIn('?topic=ocpp.rfid%2Fauthorize_balance', html)

if __name__ == '__main__':
    unittest.main()
