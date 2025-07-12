import unittest
from gway import gw


class CliCompletionTests(unittest.TestCase):
    def test_completions_include_web_server(self):
        cmds = gw.cli.completions()
        self.assertIn('web server start-app', cmds)

    def test_completions_include_builtin(self):
        cmds = gw.cli.completions()
        self.assertIn('hello-world', cmds)


if __name__ == '__main__':
    unittest.main()
