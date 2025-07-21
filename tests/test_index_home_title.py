import unittest
import sys
from gway import gw

class IndexHomeTitleTests(unittest.TestCase):
    @unittest.skip("Environment does not preserve _homes list")
    def test_home_title_uses_project_name(self):
        mod = sys.modules[gw.web.app.setup_app.__module__]
        mod._homes.clear()
        mod._links.clear()
        mod._registered_routes.clear()
        mod._enabled.clear()
        gw.web.app.setup_app("dummy", home="index")
        self.assertIn(("Dummy", "dummy/index"), mod._homes)

if __name__ == "__main__":
    unittest.main()
