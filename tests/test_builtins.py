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

    def test_recipes_builtin_lists_repository_recipes(self):
        from pathlib import Path, PurePosixPath

        recipes_dir = Path(gw.resource("recipes"))
        recipes = gw.recipes()

        self.assertIsInstance(recipes, list)
        self.assertEqual(recipes, sorted(recipes))
        self.assertEqual(len(recipes), len(set(recipes)))

        expected = {
            path.relative_to(recipes_dir).with_suffix("").as_posix()
            for pattern in ("*.gwr", "*.md")
            for path in recipes_dir.rglob(pattern)
        }

        self.assertTrue(expected.issubset(set(recipes)))

        recipes_with_ext = gw.recipes(include_extensions=True)
        self.assertEqual(recipes_with_ext, sorted(recipes_with_ext))
        self.assertEqual(len(recipes_with_ext), len(set(recipes_with_ext)))

        stripped = set()
        for entry in recipes_with_ext:
            posix_entry = PurePosixPath(entry)
            suffix = posix_entry.suffix
            self.assertIn(suffix, (".gwr", ".md", ".txt", ""))
            if suffix:
                stripped.add(posix_entry.with_suffix("").as_posix())
            else:
                stripped.add(posix_entry.as_posix())

        self.assertTrue(expected.issubset(stripped))

    def test_recipes_builtin_uses_resource_directory(self):
        import tempfile
        from pathlib import Path
        from unittest.mock import patch

        original_resource = gw.resource

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            (tmp_path / "alpha.gwr").write_text("alpha")
            (tmp_path / "notes.txt").write_text("notes")
            (tmp_path / "guide.md").write_text("guide")
            nested = tmp_path / "nested"
            nested.mkdir()
            (nested / "beta.gwr").write_text("beta")

            def fake_resource(*parts, **kwargs):
                if parts and parts[0] == "recipes":
                    return tmp_path.joinpath(*parts[1:])
                return original_resource(*parts, **kwargs)

            with patch.object(gw, "resource", new=fake_resource):
                recipes = gw.recipes()
                self.assertEqual(recipes, ["alpha", "guide", "nested/beta", "notes"])

                recipes_with_ext = gw.recipes(include_extensions=True)
                self.assertEqual(
                    recipes_with_ext,
                    ["alpha.gwr", "guide.md", "nested/beta.gwr", "notes.txt"],
                )

    def test_list_projects(self):
        project_ls = gw.projects()
        self.assertIn('clock', project_ls)
        self.assertIn('sql', project_ls)
        self.assertIn('mail', project_ls)
        self.assertIn('awg', project_ls)
        self.assertIn('cast', project_ls)
        self.assertIn('recipe', project_ls)
        self.assertIn('cdv', project_ls)

    def test_load_qr_code_project(self):
        # Normally qr is autoloaded when accessed, but this test ensures we can
        # also manually load projects and use the objects directly if we need to.
        project = gw.load_project("qr")
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
        self.assertIn("failure", flags)
        for tests in flags.values():
            self.assertIsInstance(tests, list)

    def test_abort(self):
        """Test that the abort function raises a SystemExit exception."""
        with self.assertRaises(SystemExit):
            gw.abort("Abort test")

    def test_test_install_option(self):
        """Ensure the test builtin accepts the install flag."""
        import tempfile
        import pathlib
        with tempfile.TemporaryDirectory() as tmp:
            pathlib.Path(tmp, "__init__.py").touch()
            result = builtins.test(root=tmp, install=False)
            self.assertTrue(result)

if __name__ == "__main__":
    unittest.main()
