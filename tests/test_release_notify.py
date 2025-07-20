import unittest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch
import subprocess
from gway import gw

class ReleaseBuildNotifyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.old = Path.cwd()
        os.chdir(self.base)
        Path("VERSION").write_text("0.0.1\n")
        Path("requirements.txt").write_text("requests\n")
        Path("README.rst").write_text("readme\n")

    def tearDown(self):
        os.chdir(self.old)
        self.tmp.cleanup()

    def test_notify_option_calls_notify(self):
        cp = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(gw, "test", return_value=True), \
             patch.object(gw, "resolve", return_value=""), \
             patch.object(gw.hub, "commit", return_value="abc"), \
             patch.object(gw.release, "update_changelog"), \
             patch("subprocess.run", return_value=cp), \
             patch.object(gw, "notify") as mock_notify:
            gw.release.build(notify=True)
            mock_notify.assert_called_once()

    def test_all_enables_notify(self):
        cp = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(gw, "test", return_value=True), \
             patch.object(gw, "resolve", return_value=""), \
             patch.object(gw.hub, "commit", return_value="abc"), \
             patch.object(gw.release, "update_changelog"), \
             patch.object(gw.release, "update_readme_links"), \
             patch("subprocess.run", return_value=cp), \
             patch("requests.get"), \
             patch.object(gw, "notify") as mock_notify:
            gw.release.build(all=True)
            mock_notify.assert_called_once()

if __name__ == "__main__":
    unittest.main()
