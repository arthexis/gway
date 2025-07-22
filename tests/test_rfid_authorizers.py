import unittest
import tempfile
import os
from gway import gw

class RFIDAuthorizerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.table = os.path.join(self.tmp.name, "rfids.cdv")

    def tearDown(self):
        self.tmp.cleanup()

    def _add(self, tag, balance="0", allowed=True):
        gw.cdv.update(self.table, tag, balance=str(balance), allowed="True" if allowed else "False")

    def test_authorize_balance_and_allowed(self):
        tag = "GOOD"
        self._add(tag, balance="5", allowed=True)
        payload = {"idTag": tag}
        self.assertTrue(gw.ocpp.rfid.authorize_balance(payload=payload, table=self.table))
        self.assertTrue(gw.ocpp.rfid.authorize_allowed(payload=payload, table=self.table))

    def test_denied_when_not_allowed(self):
        tag = "BLOCKED"
        self._add(tag, balance="100", allowed=False)
        payload = {"idTag": tag}
        self.assertFalse(gw.ocpp.rfid.authorize_balance(payload=payload, table=self.table))
        self.assertFalse(gw.ocpp.rfid.authorize_allowed(payload=payload, table=self.table))

    def test_balance_check_only_affects_balance_authorizer(self):
        tag = "LOWBAL"
        self._add(tag, balance="0", allowed=True)
        payload = {"idTag": tag}
        self.assertFalse(gw.ocpp.rfid.authorize_balance(payload=payload, table=self.table))
        self.assertTrue(gw.ocpp.rfid.authorize_allowed(payload=payload, table=self.table))

    def test_unknown_tag_rejected(self):
        payload = {"idTag": "MISSING"}
        self.assertFalse(gw.ocpp.rfid.authorize_balance(payload=payload, table=self.table))
        self.assertFalse(gw.ocpp.rfid.authorize_allowed(payload=payload, table=self.table))

if __name__ == "__main__":
    unittest.main()
