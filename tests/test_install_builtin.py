import unittest
import tempfile
import os
import sys
from io import StringIO
from unittest.mock import patch
import pathlib

from gway import gw


class InstallBuiltinTests(unittest.TestCase):
    def setUp(self):
        self._orig_stdout = sys.stdout
        self.stdout = StringIO()
        sys.stdout = self.stdout

    def tearDown(self):
        sys.stdout = self._orig_stdout

    def _write_script(self, path: str, *lines: str) -> None:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write("#!/usr/bin/env bash\n")
            for line in lines:
                handle.write(f"{line}\n")
        os.chmod(path, 0o755)

    def test_install_passes_recipe_and_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "install.sh")
            self._write_script(script, "echo \"args: $@\"")

            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                rc = gw.install("auto_upgrade", debug=True, force=True, root=True)

        self.assertEqual(rc, 0)
        output = self.stdout.getvalue()
        self.assertIn("args:", output)
        self.assertIn("--debug", output)
        self.assertIn("--force", output)
        self.assertIn("--root", output)
        self.assertTrue(output.strip().endswith("auto_upgrade"))

    def test_install_remove_requires_recipe(self):
        with self.assertRaises(ValueError):
            gw.install(remove=True)

    def test_install_rejects_conflicting_actions(self):
        with self.assertRaises(ValueError):
            gw.install("auto", repair=True)
        with self.assertRaises(ValueError):
            gw.install("auto", bin=True)
        with self.assertRaises(ValueError):
            gw.install("auto", shell=True)
        with self.assertRaises(ValueError):
            gw.install(repair=True, bin=True)
        with self.assertRaises(ValueError):
            gw.install(repair=True, shell=True)
        with self.assertRaises(ValueError):
            gw.install(bin=True, shell=True)

    def test_install_root_requires_recipe(self):
        with self.assertRaises(ValueError):
            gw.install(root=True)
        with self.assertRaises(ValueError):
            gw.install("auto", remove=True, root=True)

    def test_install_passes_remove_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "install.sh")
            self._write_script(script, "echo \"args: $@\"")

            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                rc = gw.install("auto_upgrade", remove=True)

        self.assertEqual(rc, 0)
        output = self.stdout.getvalue()
        self.assertIn("args: --remove auto_upgrade", output)

    def test_install_allows_bin_with_remove(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "install.sh")
            self._write_script(script, "echo \"args: $@\"")

            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                rc = gw.install("auto_upgrade", remove=True, bin=True)

        self.assertEqual(rc, 0)
        output = self.stdout.getvalue()
        self.assertIn("args: --bin --remove auto_upgrade", output)

    def test_install_allows_shell_with_remove(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "install.sh")
            self._write_script(script, "echo \"args: $@\"")

            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                rc = gw.install("auto_upgrade", remove=True, shell=True)

        self.assertEqual(rc, 0)
        output = self.stdout.getvalue()
        self.assertIn("args: --shell --remove auto_upgrade", output)

    def test_install_remove_bin_without_recipe(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "install.sh")
            self._write_script(script, "echo \"args: $@\"")

            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                rc = gw.install(remove=True, bin=True)

        self.assertEqual(rc, 0)
        output = self.stdout.getvalue()
        self.assertIn("args: --bin --remove", output)
        self.assertNotIn("auto_upgrade", output)

    def test_install_remove_shell_without_recipe(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "install.sh")
            self._write_script(script, "echo \"args: $@\"")

            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                rc = gw.install(remove=True, shell=True)

        self.assertEqual(rc, 0)
        output = self.stdout.getvalue()
        self.assertIn("args: --shell --remove", output)
        self.assertNotIn("auto_upgrade", output)

    def test_install_remove_bin_and_shell(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "install.sh")
            self._write_script(script, "echo \"args: $@\"")

            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                rc = gw.install("auto_upgrade", remove=True, bin=True, shell=True)

        self.assertEqual(rc, 0)
        output = self.stdout.getvalue()
        self.assertIn("args: --bin --shell --remove auto_upgrade", output)


if __name__ == "__main__":
    unittest.main()
