import os
import unittest
from gway import gw

class NmcliNotificationTests(unittest.TestCase):
    def test_no_admin_email_no_exception(self):
        os.environ.pop('ADMIN_EMAIL', None)
        gw.monitor.set_states('nmcli', {'wlan0_mode': 'station', 'wlan0_inet': True})
        try:
            gw.monitor.nmcli.maybe_notify_ap_switch('test')
        except Exception as e:
            self.fail(f"maybe_notify_ap_switch raised {e}")

if __name__ == '__main__':
    unittest.main()
