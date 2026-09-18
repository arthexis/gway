import unittest
import tempfile
import os
from pathlib import Path

from gway import gw


def bar():
    import pandas as pd
    return pd.__name__


def foo():
    import requests
    bar()
    return requests.__name__


class BuildRequirementsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.old_cwd = Path.cwd()
        os.chdir(self.base)

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.tmp.cleanup()

    def test_build_requirements_collects(self):
        req = gw.release.build_requirements(foo)
        self.assertTrue(req.exists())
        content = req.read_text().splitlines()
        self.assertIn('requests', content)
        self.assertIn('pandas', content)


if __name__ == '__main__':
    unittest.main()
