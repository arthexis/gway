import unittest
import os
from gway import gw

DB = "work/test_auth.duckdb"

class AuthDBTests(unittest.TestCase):
    def setUp(self):
        path = gw.resource(DB)
        if os.path.exists(path):
            os.remove(path)

    def tearDown(self):
        gw.sql.close_connection(DB, sql_engine="duckdb", project="auth_db")
        path = gw.resource(DB)
        if os.path.exists(path):
            os.remove(path)

    def test_basic_rfid_flow(self):
        uid = gw.auth_db.create_identity("Alice", dbfile=DB)
        gw.auth_db.set_basic_auth("alice", "secret", identity_id=uid, dbfile=DB)
        gw.auth_db.set_rfid("TAG1", identity_id=uid, balance=5, dbfile=DB)

        ok, ident = gw.auth_db.verify_basic("alice", "secret", dbfile=DB)
        self.assertTrue(ok)
        self.assertEqual(ident, uid)

        ok, ident2 = gw.auth_db.verify_rfid("TAG1", dbfile=DB)
        self.assertTrue(ok)
        self.assertEqual(ident2, uid)
        self.assertEqual(gw.auth_db.get_balance("TAG1", dbfile=DB), 5)

        gw.auth_db.adjust_balance("TAG1", 3, dbfile=DB)
        self.assertEqual(gw.auth_db.get_balance("TAG1", dbfile=DB), 8)

if __name__ == "__main__":
    unittest.main()
