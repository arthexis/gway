import unittest
from unittest.mock import patch
import os
from gway import gw

class HubGithubTokenTests(unittest.TestCase):
    def test_get_token_priority(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(gw.hub.get_token())
        with patch.dict(os.environ, {'REPO_TOKEN': 'a'}):
            self.assertEqual(gw.hub.get_token(), 'a')
        with patch.dict(os.environ, {'GH_TOKEN': 'b', 'REPO_TOKEN': 'a'}):
            self.assertEqual(gw.hub.get_token(), 'b')
        with patch.dict(os.environ, {'GITHUB_TOKEN': 'c', 'GH_TOKEN': 'b', 'REPO_TOKEN': 'a'}):
            self.assertEqual(gw.hub.get_token(), 'c')


class HubGitHelpersTests(unittest.TestCase):
    def test_commit_and_build_helpers(self):
        commit = gw.hub.commit()
        self.assertTrue(isinstance(commit, str) and len(commit) == 6)

        build = gw.hub.get_build()
        self.assertTrue(isinstance(build, str) and len(build) == 6)

    def test_changes_runs(self):
        diff = gw.hub.changes(max_bytes=10)
        self.assertIsInstance(diff, str)

if __name__ == '__main__':
    unittest.main()
