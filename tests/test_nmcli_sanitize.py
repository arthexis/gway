import unittest
import importlib.util
from pathlib import Path
from unittest.mock import patch

nmcli_path = Path(__file__).resolve().parents[1] / 'projects' / 'monitor' / 'nmcli.py'
spec = importlib.util.spec_from_file_location('nmcli_mod', nmcli_path)
nmcli_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(nmcli_mod)

class SanitizeHelperTests(unittest.TestCase):
    def test_sanitize_quotes(self):
        self.assertEqual(nmcli_mod._sanitize('"foo"'), 'foo')

class EnsureApProfileTests(unittest.TestCase):
    def test_ensure_ap_profile_uses_unquoted_values(self):
        calls = []
        def fake_nmcli(*args):
            calls.append(args)
            if args == ('connection', 'show'):
                return 'NAME UUID TYPE DEVICE\nmyap 123 wifi --'
            if args == ('connection', 'show', 'myap'):
                return '802-11-wireless.ssid: myssid\n802-11-wireless-security.psk: pass'
            return ''
        with patch.object(nmcli_mod, 'nmcli', side_effect=fake_nmcli):
            nmcli_mod.ensure_ap_profile('"myap"', '"myssid"', '"pass"')
        self.assertEqual(calls, [
            ('connection', 'show'),
            ('connection', 'show', 'myap'),
        ])

if __name__ == '__main__':
    unittest.main()
