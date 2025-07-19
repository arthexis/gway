import unittest
import os
import threading
from gway import gw

TEMP_DB = "work/test_duck_concurrent.duckdb"

class DuckDBConcurrencyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = gw.resource(TEMP_DB)
        if os.path.exists(path):
            os.remove(path)

    @classmethod
    def tearDownClass(cls):
        path = gw.resource(TEMP_DB)
        if os.path.exists(path):
            os.remove(path)
        gw.sql.close_connection(all=True)

    def setUp(self):
        self.conn = gw.sql.open_db(TEMP_DB, sql_engine="duckdb", project="ducktest")

    def tearDown(self):
        gw.sql.close_connection(TEMP_DB, sql_engine="duckdb", project="ducktest")

    def test_concurrent_writes(self):
        gw.sql.execute(
            "CREATE TABLE items (id INTEGER, val INTEGER)",
            connection=self.conn,
        )

        def write_db(val):
            c = gw.sql.open_db(TEMP_DB, sql_engine="duckdb", project="ducktest")
            gw.sql.execute(
                "INSERT INTO items VALUES (?, ?)",
                connection=c,
                args=(val, val),
            )
            gw.sql.close_connection(TEMP_DB, sql_engine="duckdb", project="ducktest")

        threads = [threading.Thread(target=write_db, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        rows = gw.sql.execute("SELECT count(*) FROM items", connection=self.conn)
        self.assertEqual(rows[0][0], 10)

if __name__ == "__main__":
    unittest.main()
