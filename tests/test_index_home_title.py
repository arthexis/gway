import unittest
import sys
from gway import gw

class IndexHomeTitleTests(unittest.TestCase):
    def test_home_title_uses_project_name(self):
        gw.web.app.setup_app(project="dummy", home="index")
        mod = sys.modules[gw.web.app.setup_app.__module__]
        self.assertIn(("Dummy", "dummy/index"), mod._homes)

if __name__ == "__main__":
    unittest.main()
