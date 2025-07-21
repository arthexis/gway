import unittest
import sys
from gway import gw
from paste.fixture import TestApp

class SetupAppRepeatTests(unittest.TestCase):
    def test_repeated_project_setup_creates_clean_app(self):
        mod = sys.modules[gw.web.app.setup_app.__module__]
        mod._homes.clear()
        mod._links.clear()
        mod._registered_routes.clear()
        mod._enabled.clear()
        app1 = gw.web.app.setup_app("dummy")
        TestApp(app1).get("/dummy")
        mod = sys.modules[gw.web.app.setup_app.__module__]
        self.assertEqual(mod._homes, [("Dummy", "dummy/index")])
        self.assertEqual(mod._enabled, {"dummy"})

        app2 = gw.web.app.setup_app("dummy")
        resp = TestApp(app2).get("/dummy")
        self.assertEqual(resp.status, 200)
        mod2 = sys.modules[gw.web.app.setup_app.__module__]
        self.assertEqual(mod2._homes, [("Dummy", "dummy/index")])
        self.assertEqual(mod2._enabled, {"dummy"})

if __name__ == "__main__":
    unittest.main()
