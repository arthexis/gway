import unittest
import tempfile
import os
import sys
import threading
import time
import subprocess
from io import StringIO
from unittest.mock import patch
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
            import pathlib
            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                rc = gw.upgrade("--force", "--no-test")
        self.assertEqual(rc, 0)
        self.assertIn("called with: --force --no-test", self.stdout.getvalue())

    def test_upgrade_streams_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = os.path.join(tmp, "upgrade.sh")
            with open(script, "w", encoding="utf-8") as f:
                f.write("#!/usr/bin/env bash\n")
                f.write("echo start\n")
                f.write("sleep 1\n")
                f.write("echo end\n")
            os.chmod(script, 0o755)
            import pathlib
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
            import pathlib
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
            import pathlib
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
            import pathlib
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
            import pathlib
            with patch.object(gw, "resource", return_value=pathlib.Path(script)):
                with patch("gway.builtins.core.temp_env", side_effect=failure):
                    with patch("subprocess.Popen") as mock_popen:
                        rc = gw.upgrade("--safe")
        self.assertEqual(rc, 5)
        mock_popen.assert_not_called()
        self.assertNotIn("should-not-run", self.stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
