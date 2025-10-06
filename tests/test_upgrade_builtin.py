import unittest
import tempfile
import os
import sys
import threading
import time
import subprocess
from io import StringIO
from unittest.mock import patch
import pathlib
from gway import gw


class UpgradeBuiltinTests(unittest.TestCase):
    def setUp(self):
        self.stdout = StringIO()
        self.orig_stdout = sys.stdout
        sys.stdout = self.stdout

    def tearDown(self):
        sys.stdout = self.orig_stdout

    def test_upgrade_passes_args_and_prints_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "upgrade.sh")
            with open(script, "w", encoding="utf-8") as f:
                f.write("#!/usr/bin/env bash\n")
                f.write("echo \"called with: $@\"\n")
            os.chmod(script, 0o755)
            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                rc = gw.upgrade("--force", "--latest", "--no-test")
        self.assertEqual(rc, 0)
        self.assertIn(
            "called with: --force --latest --no-test",
            self.stdout.getvalue(),
        )

    def test_upgrade_rejects_conflicting_test_flags(self):
        with patch.object(gw, "resource") as mock_resource:
            with self.assertRaises(ValueError):
                gw.upgrade("--test", "--no-test")
        mock_resource.assert_not_called()

    def test_upgrade_rejects_unknown_option(self):
        with patch.object(gw, "resource") as mock_resource:
            with self.assertRaises(ValueError):
                gw.upgrade("--invalid")
        mock_resource.assert_not_called()

    def test_upgrade_streams_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "upgrade.sh")
            with open(script, "w", encoding="utf-8") as f:
                f.write("#!/usr/bin/env bash\n")
                f.write("echo start\n")
                f.write("sleep 1\n")
                f.write("echo end\n")
            os.chmod(script, 0o755)
            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                t = threading.Thread(target=gw.upgrade)
                t.start()
                time.sleep(0.2)
                self.assertIn("start", self.stdout.getvalue())
                t.join()
        self.assertIn("end", self.stdout.getvalue())

    def test_upgrade_safe_runs_temp_env_before_script(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "upgrade.sh")
            with open(script, "w", encoding="utf-8") as f:
                f.write("#!/usr/bin/env bash\n")
                f.write("echo \"called with: $@\"\n")
            os.chmod(script, 0o755)
            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                with patch("gway.builtins.core.temp_env") as mock_temp_env:
                    rc = gw.upgrade("--safe", "--force")
        self.assertEqual(rc, 0)
        mock_temp_env.assert_called_once_with(
            "gway",
            "test",
            "--filter",
            "smoke",
            "--on-failure",
            "abort",
            pip_args="--quiet",
        )
        output = self.stdout.getvalue()
        self.assertIn("called with: --force", output)
        self.assertNotIn("--safe", output)

    def test_upgrade_safe_runs_full_suite_when_test_flag_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "upgrade.sh")
            with open(script, "w", encoding="utf-8") as f:
                f.write("#!/usr/bin/env bash\n")
                f.write("echo \"called with: $@\"\n")
            os.chmod(script, 0o755)
            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                with patch("gway.builtins.core.temp_env") as mock_temp_env:
                    rc = gw.upgrade("--safe", "--test")
        self.assertEqual(rc, 0)
        mock_temp_env.assert_called_once_with(
            "gway", "test", "--on-failure", "abort", pip_args="--quiet"
        )
        output = self.stdout.getvalue()
        self.assertIn("called with: --test", output)
        self.assertNotIn("--safe", output)

    def test_upgrade_safe_skips_temp_env_when_no_test_flag_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "upgrade.sh")
            with open(script, "w", encoding="utf-8") as f:
                f.write("#!/usr/bin/env bash\n")
                f.write("echo \"called with: $@\"\n")
            os.chmod(script, 0o755)
            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                with patch("gway.builtins.core.temp_env") as mock_temp_env:
                    rc = gw.upgrade("--safe", "--no-test")
        self.assertEqual(rc, 0)
        mock_temp_env.assert_not_called()
        output = self.stdout.getvalue()
        self.assertIn("called with: --no-test", output)
        self.assertNotIn("--safe", output)

    def test_upgrade_safe_aborts_when_temp_env_fails(self):
        failure = subprocess.CalledProcessError(5, ["gway", "test"])
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "upgrade.sh")
            with open(script, "w", encoding="utf-8") as f:
                f.write("#!/usr/bin/env bash\n")
                f.write("echo should-not-run\n")
            os.chmod(script, 0o755)
            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                with patch("gway.builtins.core.temp_env", side_effect=failure):
                    with patch("subprocess.Popen") as mock_popen:
                        rc = gw.upgrade("--safe")
        self.assertEqual(rc, 5)
        mock_popen.assert_not_called()
        self.assertNotIn("should-not-run", self.stdout.getvalue())

    def test_upgrade_normalizes_windows_path_for_bash(self):
        win_path = pathlib.PureWindowsPath("C:/Users/test/gway/upgrade.sh")

        class ImmediateThread:
            def __init__(self, target=None, args=None, **_kwargs):
                self._target = target
                self._args = args or ()

            def start(self):
                if self._target:
                    self._target(*self._args)

            def join(self):
                return None

        class DummyProcess:
            def __init__(self):
                self.stdout = StringIO("")
                self.stderr = StringIO("")
                self.returncode = 0

            def wait(self):
                return None

        fake_process = DummyProcess()

        with patch("os.name", "nt"), patch.object(
            gw, "resource", return_value=win_path
        ), patch("threading.Thread", ImmediateThread), patch(
            "gway.projects.package.gway.subprocess.Popen", return_value=fake_process
        ) as mock_popen:
            rc = gw.upgrade("--force")

        self.assertEqual(rc, 0)
        called_cmd = mock_popen.call_args[0][0]
        self.assertEqual(called_cmd[0], "bash")
        self.assertEqual(called_cmd[1], "C:/Users/test/gway/upgrade.sh")
        self.assertIn("--force", called_cmd)


if __name__ == "__main__":
    unittest.main()
