import unittest
from gway import gw

class TestMaxAwg(unittest.TestCase):
    def test_warning_when_voltage_drop_exceeds_limit(self):
        res = gw.awg.find_awg(meters=300, amps=100, volts=240, material="cu", max_lines=1, max_awg=4)
        self.assertIn("warning", res)
        self.assertEqual(res["awg"], "1")
        self.assertGreater(res["vdperc"], 3)

    def test_temperature_selection_affects_awg(self):
        r60 = gw.awg.find_awg(meters=30, amps=60, volts=240, material="cu", temperature=60)
        r75 = gw.awg.find_awg(meters=30, amps=60, volts=240, material="cu", temperature=75)
        self.assertNotEqual(r60["awg"], r75["awg"])

    def test_blank_max_awg_is_ignored(self):
        res = gw.awg.find_awg(meters=30, amps=40, max_awg="")
        self.assertEqual(res["awg"], "8")

if __name__ == "__main__":
    unittest.main()
