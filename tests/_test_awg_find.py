import unittest
import re
from gway import gw

class AWGFindCableTests(unittest.TestCase):
    """Test suite for AWG find_cable via gw integration, covering expected and consistency checks."""

    def setUp(self):
        self.func = gw["awg.find_cable"]

    def _awg_is_valid(self, awg_str):
        # Accept digit-only like "4" or digit-slash-digit like "4/0"
        return bool(re.fullmatch(r"\d+(/\d+)?", awg_str))

    # ----- Expected-value tests based on manual CSV data -----
    def test_expected_cu_8_awg_65m_20a(self):
        result = self.func(material="cu", meters=65, amps=20, volts=220, phases=3)
        gw.debug(f"expected_cu_8_awg_65m_20a {result=}")
        self.assertEqual(result['awg'], '8')
        self.assertAlmostEqual(result['vdrop'], 5.3586, places=4)
        self.assertAlmostEqual(result['vdperc'], 2.44, places=2)

    def test_expected_cu_6_awg_65m_40a_case1(self):
        result = self.func(material="cu", meters=65, amps=40, volts=220, phases=3)
        gw.debug(f"expected_cu_6_awg_65m_40a_case1 {result=}")
        self.assertEqual(result['awg'], '6')
        self.assertAlmostEqual(result['vdrop'], 6.7392, places=4)
        self.assertAlmostEqual(result['vdperc'], 3.06, places=2)

    def test_expected_cu_6_awg_65m_40a_case2(self):
        result = self.func(material="cu", meters=65, amps=40, volts=220, phases=3)
        gw.debug(f"expected_cu_6_awg_65m_40a_case2 {result=}")
        self.assertEqual(result['awg'], '6')
        self.assertAlmostEqual(result['vdrop'], 10.5680, places=4)
        self.assertAlmostEqual(result['vdperc'], 4.71, places=2)

    def test_expected_cu_4_awg_65m_40a(self):
        result = self.func(material="cu", meters=65, amps=40, volts=220, phases=3)
        gw.debug(f"expected_cu_4_awg_65m_40a {result=}")
        self.assertIn(result['awg'], ('4', '4/0'))  # accept '4/0' too
        self.assertAlmostEqual(result['vdrop'], 6.5216, places=4)
        self.assertAlmostEqual(result['vdperc'], 2.96, places=2)

    def test_expected_cu_4_awg_150m_20a(self):
        result = self.func(material="cu", meters=150, amps=20, volts=220, phases=3)
        gw.debug(f"expected_cu_4_awg_150m_20a {result=}")
        self.assertIn(result['awg'], ('4', '4/0'))  # accept '4/0' too
        self.assertAlmostEqual(result['vdrop'], 4.8912, places=4)
        self.assertAlmostEqual(result['vdperc'], 2.22, places=2)

    # ----- Consistency checks -----
    def test_consistency_vdrop_relations(self):
        # Random valid call
        result = self.func(material="cu", meters=100, amps=30, volts=220, phases=3)
        gw.debug(f"consistency_vdrop_relations {result=}")
        self.assertTrue(self._awg_is_valid(result['awg']))
        self.assertAlmostEqual(result['vdrop'], result['vdperc'] * 220 / 100, places=4)
        self.assertAlmostEqual(result['vend'], 220 - result['vdrop'], places=4)

    # ----- Basic integration smoke test -----
    def test_valid_basic_call(self):
        result = self.func(material="cu", meters=40, amps=40, volts=220, phases=3)
        gw.debug(f"valid_basic_call {result=}")
        expected_keys = {'awg', 'vdrop', 'vdperc', 'vend', 'cables', 'cable_m'}
        self.assertTrue(expected_keys.issubset(result))

    # ----- Negative tests for input validations -----
    def test_amps_below_min_raises(self):
        with self.assertRaises(AssertionError) as ctx:
            self.func(material="cu", meters=10, amps=10, volts=220, phases=1)
        gw.debug(f"amps_below_min {ctx.exception=}")
        self.assertIn('Min. charger load is 20 Amps', str(ctx.exception))

    def test_meters_below_min_raises(self):
        with self.assertRaises(AssertionError) as ctx:
            self.func(material="cu", meters=0, amps=40, volts=220, phases=1)
        gw.debug(f"meters_below_min {ctx.exception=}")
        self.assertIn('at least 1 meter', str(ctx.exception))

    def test_volt_out_of_range_raises(self):
        with self.assertRaises(AssertionError) as ctx_low:
            self.func(material="cu", meters=10, amps=40, volts=100, phases=1)
        gw.debug(f"volt_low {ctx_low.exception=}")
        with self.assertRaises(AssertionError) as ctx_high:
            self.func(material="cu", meters=10, amps=40, volts=500, phases=1)
        gw.debug(f"volt_high {ctx_high.exception=}")
        self.assertIn('Volt range is 110-460', str(ctx_low.exception))
        self.assertIn('Volt range is 110-460', str(ctx_high.exception))

    def test_invalid_material_raises(self):
        with self.assertRaises(AssertionError) as ctx:
            self.func(material="xx", meters=10, amps=40, volts=220, phases=1)
        gw.debug(f"invalid_material {ctx.exception=}")
        self.assertIn('Material must be cu, al or ?', str(ctx.exception))

    def test_invalid_phases_raises(self):
        with self.assertRaises(AssertionError) as ctx:
            self.func(material="cu", meters=10, amps=40, volts=220, phases=2)
        gw.debug(f"invalid_phases {ctx.exception=}")
        self.assertIn('Allowed phases 1 or 3', str(ctx.exception))


if __name__ == '__main__':
    unittest.main()
