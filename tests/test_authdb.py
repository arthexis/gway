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
        gw.sql.close_connection(DB, sql_engine="duckdb", project="authdb")
        path = gw.resource(DB)
        if os.path.exists(path):
            os.remove(path)

    def test_basic_rfid_flow(self):
        uid = gw.authdb.create_identity("Alice", dbfile=DB)
        gw.authdb.set_basic_auth("alice", "secret", identity_id=uid, dbfile=DB)
        gw.authdb.set_rfid("TAG1", identity_id=uid, balance=5, dbfile=DB)

        ok, ident = gw.authdb.verify_basic("alice", "secret", dbfile=DB)
        self.assertTrue(ok)
        self.assertEqual(ident, uid)

        ok, ident2 = gw.authdb.verify_rfid("TAG1", dbfile=DB)
        self.assertTrue(ok)
        self.assertEqual(ident2, uid)
        self.assertEqual(gw.authdb.get_balance("TAG1", dbfile=DB), 5)

        gw.authdb.adjust_balance("TAG1", 3, dbfile=DB)
        self.assertEqual(gw.authdb.get_balance("TAG1", dbfile=DB), 8)

if __name__ == "__main__":
    unittest.main()
