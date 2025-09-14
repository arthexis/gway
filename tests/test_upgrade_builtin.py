import unittest
import tempfile
import os
import sys
import threading
import time
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


if __name__ == "__main__":
    unittest.main()
