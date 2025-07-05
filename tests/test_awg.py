import unittest
from gway import gw

def awg_val(s):
    return -int(s.split('/')[0]) if '/' in s else int(s)

class TestMaxAwg(unittest.TestCase):
    def test_warning_when_voltage_drop_exceeds_limit(self):
        res = gw.awg.find_awg(meters=250, amps=60, volts=240, material="cu", max_awg=4)
        self.assertIn("warning", res)
        self.assertEqual(res["awg"], "4")
        self.assertGreater(res["vdperc"], 3)

    def test_uses_extra_lines_within_limit(self):
        res = gw.awg.find_awg(meters=125, amps=60, volts=240, material="cu", max_awg=4, max_lines=3)
        self.assertEqual(res["awg"], "4")
        self.assertEqual(res["lines"], 2)
        self.assertLess(res["vdperc"], 3)

    def test_respects_max_awg_limit(self):
        res = gw.awg.find_awg(meters=250, amps=125, volts=240, material="cu", max_awg=4)
        self.assertEqual(res["awg"], "n/a")

    def test_temperature_selection_affects_awg(self):
        r60 = gw.awg.find_awg(meters=30, amps=60, volts=240, material="cu", temperature=60)
        r75 = gw.awg.find_awg(meters=30, amps=60, volts=240, material="cu", temperature=75)
        self.assertNotEqual(r60["awg"], r75["awg"])

    def test_blank_max_awg_is_ignored(self):
        res = gw.awg.find_awg(meters=30, amps=40, max_awg="")
        self.assertEqual(res["awg"], "8")

    def test_blank_max_lines_defaults_to_one(self):
        res = gw.awg.find_awg(meters=30, amps=40, max_lines="")
        self.assertEqual(res["lines"], 1)

if __name__ == "__main__":
    unittest.main()
