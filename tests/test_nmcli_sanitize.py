import unittest
from unittest.mock import patch
from pathlib import Path
import importlib.util

class SanitizeHelperTests(unittest.TestCase):
    @staticmethod
    def _load_nmcli():
        nmcli_path = Path(__file__).resolve().parents[1] / 'projects' / 'monitor' / 'nmcli.py'
        spec = importlib.util.spec_from_file_location('nmcli_mod', nmcli_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    @classmethod
    def setUpClass(cls):
        cls.nmcli_mod = cls._load_nmcli()
    def test_sanitize_quotes(self):
        self.assertEqual(self.nmcli_mod._sanitize('"foo"'), 'foo')

class EnsureApProfileTests(unittest.TestCase):
    @staticmethod
    def _load_nmcli():
        nmcli_path = Path(__file__).resolve().parents[1] / 'projects' / 'monitor' / 'nmcli.py'
        spec = importlib.util.spec_from_file_location('nmcli_mod', nmcli_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    @classmethod
    def setUpClass(cls):
        cls.nmcli_mod = cls._load_nmcli()
    def test_ensure_ap_profile_uses_unquoted_values(self):
        calls = []
        def fake_nmcli(*args):
            calls.append(args)
            if args == ('-t', '-f', 'NAME,UUID,TYPE,DEVICE', 'connection', 'show'):
                return 'myap:123:wifi:\n'
            if args == ('connection', 'show', 'myap'):
                return '802-11-wireless.ssid: myssid\n802-11-wireless-security.psk: pass'
            return ''
        with patch.object(self.nmcli_mod, 'nmcli', side_effect=fake_nmcli):
            self.nmcli_mod.ensure_ap_profile('"myap"', '"myssid"', '"pass"')
        self.assertEqual(calls, [
            ('-t', '-f', 'NAME,UUID,TYPE,DEVICE', 'connection', 'show'),
            ('connection', 'show', 'myap'),
        ])

    def test_ensure_ap_profile_sets_default_ip(self):
        calls = []
        def fake_nmcli(*args):
            calls.append(args)
            return ''
        with patch.object(self.nmcli_mod, 'nmcli', side_effect=fake_nmcli):
            self.nmcli_mod.ensure_ap_profile('ap', 'ssid', 'pass')
        self.assertIn(
            (
                'connection',
                'modify',
                'ap',
                'mode',
                'ap',
                '802-11-wireless.band',
                'bg',
                'wifi-sec.key-mgmt',
                'wpa-psk',
                'wifi-sec.psk',
                'pass',
                'ipv4.method',
                'shared',
                'ipv4.addresses',
                '10.42.0.1/24',
            ),
            calls,
        )

if __name__ == '__main__':
    unittest.main()
