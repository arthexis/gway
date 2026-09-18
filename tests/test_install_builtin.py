import unittest
import tempfile
import os
import sys
from io import StringIO
from types import SimpleNamespace
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
            if os.name == "nt":
                handle.write("@echo off\n")
            else:
                handle.write("#!/usr/bin/env bash\n")
            for line in lines:
                handle.write(f"{line}\n")
        if os.name != "nt":
            os.chmod(path, 0o755)

    def _install_script(self, directory: str) -> str:
        if os.name == "nt":
            script = os.path.join(directory, "install.bat")
            self._write_script(script, "echo args: %*")
        else:
            script = os.path.join(directory, "install.sh")
            self._write_script(script, 'echo "args: $@"')
        return script

    def test_install_passes_recipe_and_flags(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = self._install_script(tmp)

            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                rc = gw.install("auto_upgrade", debug=True, force=True, root=True)

        self.assertEqual(rc, 0)
        output = self.stdout.getvalue()
        self.assertIn("args:", output)
        self.assertIn("--debug", output)
        self.assertIn("--force", output)
        self.assertIn("--root", output)
        self.assertTrue(output.strip().endswith("auto_upgrade"))

    def test_install_forwards_recipe_args(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = self._install_script(tmp)

            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                rc = gw.install("auto_upgrade", "--latest", "--interval", "5")

        self.assertEqual(rc, 0)
        output = self.stdout.getvalue()
        self.assertIn("--latest", output)
        self.assertIn("--interval", output)
        self.assertTrue(output.strip().endswith("5"))

    def test_install_pip_mode_defaults_to_gway(self):
        result = SimpleNamespace(returncode=0)
        with patch.object(sys, "executable", "/opt/python"), patch(
            "subprocess.run", return_value=result
        ) as run_mock:
            rc = gw.install(mode="pip")

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args[0][0]
        self.assertEqual(cmd[:4], ["/opt/python", "-m", "pip", "install"])
        self.assertIn("--quiet", cmd)
        self.assertIn("--upgrade", cmd)
        self.assertIn("gway", cmd)

    def test_install_pip_mode_honours_latest_flag(self):
        result = SimpleNamespace(returncode=0)
        gw.context["auto_upgrade_latest"] = True
        try:
            with patch("subprocess.run", return_value=result) as run_mock:
                gw.install(mode="pip")
        finally:
            gw.context.clear()

        cmd = run_mock.call_args[0][0]
        self.assertIn("--force-reinstall", cmd)

        with patch("subprocess.run", return_value=result) as run_mock:
            gw.install(mode="pip", latest=False)

        self.assertNotIn("--force-reinstall", run_mock.call_args[0][0])

    def test_install_pip_mode_rejects_service_flags(self):
        with self.assertRaises(ValueError):
            gw.install(mode="pip", remove=True, bin=True)
        with self.assertRaises(ValueError):
            gw.install(mode="pip", root=True)

    def test_install_pip_mode_supports_remove(self):
        result = SimpleNamespace(returncode=0)
        with patch.object(sys, "executable", "/opt/python"), patch(
            "subprocess.run", return_value=result
        ) as run_mock:
            rc = gw.install(mode="pip", remove=True)

        self.assertEqual(rc, 0)
        cmd = run_mock.call_args[0][0]
        self.assertEqual(cmd[:4], ["/opt/python", "-m", "pip", "uninstall"])
        self.assertIn("-y", cmd)
        self.assertIn("gway", cmd)

    def test_install_pip_mode_repair_forces_reinstall(self):
        result = SimpleNamespace(returncode=0)
        with patch.object(sys, "executable", "/opt/python"), patch(
            "subprocess.run", return_value=result
        ) as run_mock:
            gw.install("custom", mode="pip", repair=True)

        cmd = run_mock.call_args[0][0]
        self.assertEqual(cmd[:4], ["/opt/python", "-m", "pip", "install"])
        self.assertIn("--force-reinstall", cmd)
        self.assertIn("custom", cmd)

    def test_install_remove_requires_recipe(self):
        with self.assertRaises(ValueError):
            gw.install(remove=True)

    def test_install_recipe_args_require_recipe(self):
        with self.assertRaises(ValueError):
            gw.install(None, "--latest")

    def test_install_rejects_conflicting_actions(self):
        with self.assertRaises(ValueError):
            gw.install("auto", repair=True)
        with self.assertRaises(ValueError):
            gw.install("auto", bin=True)
        with self.assertRaises(ValueError):
            gw.install(repair=True, bin=True)

    def test_install_root_requires_recipe(self):
        with self.assertRaises(ValueError):
            gw.install(root=True)
        with self.assertRaises(ValueError):
            gw.install("auto", remove=True, root=True)

    def test_install_passes_remove_flag(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = self._install_script(tmp)

            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                rc = gw.install("auto_upgrade", remove=True)

        self.assertEqual(rc, 0)
        output = self.stdout.getvalue()
        self.assertIn("args: --remove auto_upgrade", output)

    def test_install_allows_bin_with_remove(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = self._install_script(tmp)

            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                rc = gw.install("auto_upgrade", remove=True, bin=True)

        self.assertEqual(rc, 0)
        output = self.stdout.getvalue()
        self.assertIn("args: --bin --remove auto_upgrade", output)

    def test_install_remove_bin_without_recipe(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = self._install_script(tmp)

            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                rc = gw.install(remove=True, bin=True)

        self.assertEqual(rc, 0)
        output = self.stdout.getvalue()
        self.assertIn("args: --bin --remove", output)
        self.assertNotIn("auto_upgrade", output)


if __name__ == "__main__":
    unittest.main()
