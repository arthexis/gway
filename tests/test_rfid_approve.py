import unittest
import os
import tempfile
from gway import gw

# Ensure project functions are available
gw.load_project("ocpp.rfid")


class RFIDApproveTests(unittest.TestCase):
    TABLE = "work/test_rfids_approve.cdv"

    def setUp(self):
        path = gw.resource(self.TABLE)
        if os.path.exists(path):
            os.remove(path)

    def tearDown(self):
        path = gw.resource(self.TABLE)
        if os.path.exists(path):
            os.remove(path)

    def test_approve_allows_valid_tag(self):
        gw.ocpp.rfid.create_entry("OK", balance=2, allowed=True, table=self.TABLE)
        payload = {"idTag": "OK"}
        self.assertTrue(gw.ocpp.rfid.approve(payload=payload, table=self.TABLE))

    def test_approve_rejects_unknown_tag(self):
        payload = {"idTag": "MISSING"}
        self.assertFalse(gw.ocpp.rfid.approve(payload=payload, table=self.TABLE))

    def test_approve_rejects_low_balance(self):
        gw.ocpp.rfid.create_entry("LOW", balance=0, allowed=True, table=self.TABLE)
        payload = {"idTag": "LOW"}
        self.assertFalse(gw.ocpp.rfid.approve(payload=payload, table=self.TABLE))

    def test_approve_rejects_not_allowed(self):
        gw.ocpp.rfid.create_entry("BLOCK", balance=5, allowed=False, table=self.TABLE)
        payload = {"idTag": "BLOCK"}
        self.assertFalse(gw.ocpp.rfid.approve(payload=payload, table=self.TABLE))

    def test_approve_with_auth_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            dbfile = os.path.join(tmp, "auth.duckdb")
            uid = gw.auth_db.create_identity(dbfile=dbfile)
            gw.auth_db.set_rfid("TAG", identity_id=uid, balance=5, allowed=True, dbfile=dbfile)
            payload = {"idTag": "TAG"}
            self.assertTrue(gw.ocpp.rfid.approve(payload=payload, dbfile=dbfile))
            gw.auth_db.set_rfid("TAG", identity_id=uid, balance=0, allowed=True, dbfile=dbfile)
            self.assertFalse(gw.ocpp.rfid.approve(payload=payload, dbfile=dbfile))
            gw.auth_db.set_rfid("TAG", identity_id=uid, balance=5, allowed=False, dbfile=dbfile)
            self.assertFalse(gw.ocpp.rfid.approve(payload=payload, dbfile=dbfile))
            gw.sql.close_db(dbfile, sql_engine="duckdb", project="auth_db")


if __name__ == "__main__":
    unittest.main()
