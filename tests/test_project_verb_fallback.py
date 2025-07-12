import unittest
from gway import gw

class ProjectVerbFallbackTests(unittest.TestCase):
    def test_single_word_function_fallback(self):
        app_direct = gw.web.app.setup_app("dummy")
        app_alias = gw.web.app.setup("dummy")
        self.assertEqual(type(app_alias), type(app_direct))

if __name__ == "__main__":
    unittest.main()
