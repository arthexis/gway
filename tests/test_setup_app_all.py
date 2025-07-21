import unittest
from gway import gw

class SetupAppAllTests(unittest.TestCase):
    def test_delegates_subprojects(self):
        app = gw.web.app.setup_app("ocpp", all=True)
        bottle_app = app[0] if isinstance(app, tuple) else app
        has_csms_route = any(r.rule.startswith('/ocpp/csms/') for r in bottle_app.routes)
        self.assertTrue(has_csms_route, "csms routes not registered")

if __name__ == "__main__":
    unittest.main()
