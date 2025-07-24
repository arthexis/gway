import unittest
import os
import importlib
from gway import gw

gw.load_project("ocpp.data")
import ocpp_data

from gway.builtins import is_test_flag


@unittest.skipUnless(is_test_flag("ocpp"), "OCPP tests disabled")
class OcppDataTests(unittest.TestCase):
    DB = "work/test_ocpp.duckdb"

    def setUp(self):
        self.old_db = ocpp_data.DBFILE
        ocpp_data.DBFILE = self.DB
        self.sql_mod = importlib.import_module(gw.sql.open_db.__module__)
        self.old_cfg = self.sql_mod._db_configs.get("ocpp")
        self.sql_mod._db_configs.pop("ocpp", None)
        path = gw.resource(self.DB)
        if os.path.exists(path):
            os.remove(path)

    def tearDown(self):
        gw.sql.close_db(all=True)
        if self.old_cfg is not None:
            self.sql_mod._db_configs["ocpp"] = self.old_cfg
        else:
            self.sql_mod._db_configs.pop("ocpp", None)
        path = gw.resource(self.DB)
        if os.path.exists(path):
            os.remove(path)
        ocpp_data.DBFILE = self.old_db

    def test_basic_record_cycle(self):
        ocpp_data.record_transaction_start("A", 1, 100)
        ocpp_data.record_meter_value("A", 1, 105, "Energy.Active.Import.Register", 500, "Wh")
        ocpp_data.record_transaction_stop("A", 1, 110, meter_stop=550)
        rows = list(ocpp_data.iter_transactions("A"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][1], 1)
        mv = ocpp_data.get_latest_meter_value("A", 1)
        self.assertAlmostEqual(mv, 0.55, places=2)

    def test_connections_column_added(self):
        conn = gw.sql.open_db(self.DB, sql_engine=ocpp_data.ENGINE, project="ocpp")
        gw.sql.execute(
            "CREATE TABLE connections(\n"
            " charger_id TEXT PRIMARY KEY, connected INTEGER, last_heartbeat TEXT,\n"
            " status TEXT, error_code TEXT, info TEXT\n)",
            connection=conn,
        )
        gw.sql.close_db(self.DB, project="ocpp", sql_engine=ocpp_data.ENGINE)
        ocpp_data.set_connection_status("B", True)
        ocpp_data.record_last_msg("B", 123)
        conn = gw.sql.open_db(project="ocpp")
        cols = [r[1] for r in gw.sql.execute("PRAGMA table_info(connections)", connection=conn)]
        self.assertIn("last_msg", cols)

    def test_get_summary_without_tables(self):
        """get_summary should work when no data has been recorded yet."""
        rows = ocpp_data.get_summary()
        self.assertEqual(rows, [])

if __name__ == "__main__":
    unittest.main()
