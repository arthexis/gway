import unittest

import importlib.util
from pathlib import Path

svc_path = Path(__file__).resolve().parents[1] / 'tools' / 'windows_service.py'
spec = importlib.util.spec_from_file_location('windows_service', svc_path)
ws = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ws)


class FormatDisplayNameTests(unittest.TestCase):
    def test_format_display_name(self):
        self.assertEqual(ws._format_display_name('gway-etron-local'), 'GWAY Etron Local')
        self.assertEqual(ws._format_display_name('foo_bar-baz'), 'Foo Bar Baz')


class ParseArgsTests(unittest.TestCase):
    def test_parse_args_user_password(self):
        args = ws.parse_args([
            'install',
            '--name', 'svc',
            '--recipe', 'demo',
            '--user', 'testuser',
            '--password', 'secret',
        ])
        self.assertEqual(args.user, 'testuser')
        self.assertEqual(args.password, 'secret')


if __name__ == '__main__':
    unittest.main()
