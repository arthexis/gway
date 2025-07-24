import unittest
import tempfile
import os
from pathlib import Path
from unittest.mock import patch
import subprocess

from gway import gw


class ReleaseBuildTagTests(unittest.TestCase):
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

    def test_tag_creates_git_tag(self):
        cp = subprocess.CompletedProcess([], 0, "", "")
        with patch.object(gw, "test", return_value=True), \
             patch.object(gw, "resolve", return_value=""), \
             patch.object(gw.hub, "commit", return_value="abc"), \
             patch.object(gw.release, "update_changelog"), \
             patch("subprocess.run", return_value=cp) as mock_run:
            gw.release.build(git=True, tag=True)
            mock_run.assert_any_call(["git", "tag", "v0.0.1"], check=True)
            mock_run.assert_any_call(["git", "push", "origin", "v0.0.1"], check=True)


if __name__ == "__main__":
    unittest.main()

