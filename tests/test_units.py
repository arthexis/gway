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

    def test_interval_alias_seconds_and_minutes(self):
        cmds = [['monitor', 'start-watch', 'rpi', '--no-daemon', '--interval', '60']]
        process(cmds)
        expected = gw.monitor.get_next_check_time('rpi')

        cmds = [['monitor', 'start-watch', 'rpi', '--no-daemon', '--seconds', '60']]
        process(cmds)
        self.assertEqual(gw.monitor.get_next_check_time('rpi'), expected)

        cmds = [['monitor', 'start-watch', 'rpi', '--no-daemon', '--minutes', '1']]
        process(cmds)
        self.assertEqual(gw.monitor.get_next_check_time('rpi'), expected)

if __name__ == '__main__':
    unittest.main()
