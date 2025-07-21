import unittest
from gway import gw

class SetupAppEverythingTests(unittest.TestCase):
    def test_delegates_subprojects(self):
        app = gw.web.app.setup_app("ocpp", everything=True)
        bottle_app = app[0] if isinstance(app, tuple) else app
        has_csms_route = any(r.rule.startswith('/ocpp/csms/') for r in bottle_app.routes)
        self.assertTrue(has_csms_route, "csms routes not registered")

    def test_subproject_view_resolution(self):
        self.assertFalse(hasattr(gw.ocpp, 'view_active_chargers'))
        app = gw.web.app.setup_app("ocpp", everything=True)
        bottle_app = app[0] if isinstance(app, tuple) else app
        generic_route = next((r for r in bottle_app.routes if r.rule == '/ocpp/<view:path>'), None)
        self.assertIsNotNone(generic_route, 'generic ocpp view route missing')

if __name__ == "__main__":
    unittest.main()
