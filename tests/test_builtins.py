# tests/test_builtins.py

# These tests are for builtins, but to test a project such as sql use:
# gw.sql.function directly, you don't need to import the project or function.

import unittest
import sys
import io
from gway.gateway import gw
import gway.builtins as builtins

class GatewayBuiltinsTests(unittest.TestCase):

    def setUp(self):
        # Redirect stdout to capture printed messages
        self.sio = io.StringIO()
        sys.stdout = self.sio

    def tearDown(self):
        # Restore stdout
        sys.stdout = sys.__stdout__

    def test_builtins_functions(self):
        # Test if the builtins can be accessed directly and are callable
        try:
            builtins.hello_world()
        except AttributeError as e:
            self.fail(f"AttributeError occurred: {e}")

    def test_list_builtins(self):
        # Test if the builtins can be accessed directly and are callable
        builtin_ls = gw.builtins()
        self.assertIn('help', builtin_ls)
        self.assertIn('test', builtin_ls)
        self.assertIn('abort', builtin_ls)
        self.assertIn('run_recipe', builtin_ls)

    def test_list_projects(self):
        project_ls = gw.projects()
        self.assertIn('web', project_ls)
        self.assertIn('clock', project_ls)
        self.assertIn('sql', project_ls)
        self.assertIn('mail', project_ls)
        self.assertIn('awg', project_ls)
        self.assertIn('cast', project_ls)
        self.assertIn('games', project_ls)
        self.assertIn('recipe', project_ls)
        self.assertIn('cdv', project_ls)

    def test_load_qr_code_project(self):
        # Normally qr is autoloaded when accessed, but this test ensures we can
        # also manually load projects and use the objects directly if we need to.
        project = gw.load_project("studio.qr")
        test_url = project.generate_url("test")
        self.assertTrue(test_url.endswith(".png"))

    def test_hello_world(self):
        # Call the hello_world function
        # Note we don't have to import it, its just a GWAY builtin.
        gw.hello_world()

        # Check if "Hello, World!" was printed
        self.assertIn("Hello, World!", self.sio.getvalue().strip())

    def test_help_hello_world(self):
        # Help is a builtin
        help_result = gw.help('hello-world')
        self.assertEqual(help_result['Sample CLI'], 'gway hello-world')

    def test_help_list_flags(self):
        flags = gw.help(list_flags=True)["Test Flags"]
        expected = {"failure", "ocpp", "proxy", "screen"}
        self.assertEqual(set(flags.keys()), expected)
        for tests in flags.values():
            self.assertIsInstance(tests, list)

    def test_abort(self):
        """Test that the abort function raises a SystemExit exception."""
        with self.assertRaises(SystemExit):
            gw.abort("Abort test")

if __name__ == "__main__":
    unittest.main()
