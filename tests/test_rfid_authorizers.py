import unittest
import tempfile
import os
from gway import gw

class RFIDAuthorizerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "auth.duckdb")

    def tearDown(self):
        gw.sql.close_connection(self.db, sql_engine="duckdb", project="auth_db")
        self.tmp.cleanup()

    def _add(self, tag, balance="0", allowed=True):
        uid = gw.auth_db.create_identity(tag, dbfile=self.db)
        gw.auth_db.set_rfid(tag, identity_id=uid, balance=float(balance), allowed=allowed, dbfile=self.db)

    def test_authorize_balance_and_allowed(self):
        tag = "GOOD"
        self._add(tag, balance="5", allowed=True)
        payload = {"idTag": tag}
        self.assertTrue(gw.ocpp.rfid.authorize_balance(payload=payload, dbfile=self.db))
        self.assertTrue(gw.ocpp.rfid.authorize_allowed(payload=payload, dbfile=self.db))

    def test_denied_when_not_allowed(self):
        tag = "BLOCKED"
        self._add(tag, balance="100", allowed=False)
        payload = {"idTag": tag}
        self.assertFalse(gw.ocpp.rfid.authorize_balance(payload=payload, dbfile=self.db))
        self.assertFalse(gw.ocpp.rfid.authorize_allowed(payload=payload, dbfile=self.db))

    def test_balance_check_only_affects_balance_authorizer(self):
        tag = "LOWBAL"
        self._add(tag, balance="0", allowed=True)
        payload = {"idTag": tag}
        self.assertFalse(gw.ocpp.rfid.authorize_balance(payload=payload, dbfile=self.db))
        self.assertTrue(gw.ocpp.rfid.authorize_allowed(payload=payload, dbfile=self.db))

    def test_unknown_tag_rejected(self):
        payload = {"idTag": "MISSING"}
        self.assertFalse(gw.ocpp.rfid.authorize_balance(payload=payload, dbfile=self.db))
        self.assertFalse(gw.ocpp.rfid.authorize_allowed(payload=payload, dbfile=self.db))

if __name__ == "__main__":
    unittest.main()
