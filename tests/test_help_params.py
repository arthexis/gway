import unittest
from gway import gw


class HelpParamTests(unittest.TestCase):
    def test_help_parameters_and_providers(self):
        gw.help_db.build(update=True)
        gw.sql.close_db(all=True)
        mod = __import__(gw.web.app.setup_app.__module__)
        saved_enabled = getattr(mod, "_enabled", set()).copy()
        saved_homes = getattr(mod, "_homes", []).copy()
        info = gw.help("web.auto", "get-driver")
        # Restore state altered by loading projects
        if hasattr(mod, "_enabled"):
            mod._enabled = saved_enabled
        if hasattr(mod, "_homes"):
            mod._homes = saved_homes
        self.assertIn("Parameters", info)
        params = {p["name"]: p for p in info["Parameters"]}
        self.assertIn("browser", params)
        self.assertEqual(params["browser"]["type"], "str")
        self.assertEqual(info.get("Returns"), "selenium.webdriver.Remote")
        self.assertEqual(info.get("Provides"), "selenium.webdriver.Remote")


if __name__ == "__main__":
    unittest.main()

