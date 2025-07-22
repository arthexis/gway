import unittest
import os
from gway import gw

# Load the project to access helper functions
gw.load_project("ocpp.rfid")
import ocpp_rfid

class RFIDHelperTests(unittest.TestCase):
    TABLE = "work/test_rfids.cdv"

    def setUp(self):
        path = gw.resource(self.TABLE)
        if os.path.exists(path):
            os.remove(path)

    def tearDown(self):
        path = gw.resource(self.TABLE)
        if os.path.exists(path):
            os.remove(path)

    def test_basic_entry_cycle(self):
        ocpp_rfid.create_entry("TAG1", balance=10, allowed=True, user="foo", table=self.TABLE)
        recs = gw.cdv.load_all(self.TABLE)
        self.assertEqual(recs["TAG1"].get("balance"), "10")
        self.assertEqual(recs["TAG1"].get("user"), "foo")
        self.assertEqual(recs["TAG1"].get("allowed"), "True")

        ocpp_rfid.update_entry("TAG1", table=self.TABLE, user="bar")
        self.assertEqual(gw.cdv.load_all(self.TABLE)["TAG1"].get("user"), "bar")

        ocpp_rfid.disable("TAG1", table=self.TABLE)
        self.assertEqual(gw.cdv.load_all(self.TABLE)["TAG1"].get("allowed"), "False")
        ocpp_rfid.enable("TAG1", table=self.TABLE)
        self.assertEqual(gw.cdv.load_all(self.TABLE)["TAG1"].get("allowed"), "True")

        self.assertTrue(ocpp_rfid.credit("TAG1", 5, table=self.TABLE))
        self.assertEqual(gw.cdv.load_all(self.TABLE)["TAG1"].get("balance"), "15.0")
        self.assertTrue(ocpp_rfid.debit("TAG1", 3, table=self.TABLE))
        self.assertEqual(gw.cdv.load_all(self.TABLE)["TAG1"].get("balance"), "12.0")

        ocpp_rfid.delete_entry("TAG1", table=self.TABLE)
        self.assertEqual(gw.cdv.load_all(self.TABLE), {})

if __name__ == "__main__":
    unittest.main()
