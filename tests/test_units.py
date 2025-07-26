import unittest
from gway.console import process
from gway import gw

class UnitConversionTests(unittest.TestCase):
    def test_yards_flag_converts_to_meters(self):
        cmds = [['awg', 'find-awg', '--yards', '30', '--amps', '60']]
        _, result = process(cmds)
        expected = gw.awg.find_awg(meters=27, amps=60)
        self.assertEqual(result['awg'], expected['awg'])
        self.assertEqual(result['meters'], expected['meters'])

if __name__ == '__main__':
    unittest.main()
