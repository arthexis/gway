import unittest
import os
import sqlite3
import tempfile
from gway.gateway import gw


class GatewaySQLTests(unittest.TestCase):

    def setUp(self):
        self.db_fd, self.db_path = tempfile.mkstemp(suffix=".sqlite")
        self.db_name = os.path.basename(self.db_path)
        self.db_key = f"temp/{self.db_name}"
        self.csv_dir = "data/test_csv"
        os.makedirs(self.csv_dir, exist_ok=True)
        with open(f"{self.csv_dir}/sample.csv", "w") as f:
            f.write("id,name\n1,Alice\n2,Bob")

    def tearDown(self):
        try:
            gw.sql.close_connection(datafile=self.db_key)
        except Exception:
            pass
        os.close(self.db_fd)
        os.remove(self.db_path)

    def test_connect_and_disconnect(self):
        conn = gw.sql.open_connection(datafile=self.db_key)
        self.assertIsInstance(conn.cursor(), sqlite3.Cursor)
        gw.sql.close_connection(datafile=self.db_key)

    def test_execute_sql(self):
        conn = gw.sql.open_connection(datafile=self.db_key)
        with conn as cursor:
            cursor.execute("CREATE TABLE test (id INTEGER, name TEXT)")
        result = gw.sql.execute("INSERT INTO test VALUES (1, 'Alpha')")
        self.assertIsNone(result)
        rows = gw.sql.execute("SELECT * FROM test")
        self.assertEqual(rows, [(1, 'Alpha')])

    def test_autoload_csv(self):
        conn = gw.sql.open_connection(datafile=self.db_key, autoload=True, force=True)
        gw.sql.load_csv(folder=self.csv_dir, force=True)
        rows = gw.sql.execute("SELECT * FROM sample")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0][1], "Alice")

    def test_reuse_connection(self):
        conn1 = gw.sql.open_connection(datafile=self.db_key)
        conn2 = gw.sql.open_connection(datafile=self.db_key)
        self.assertIs(conn1, conn2)

    def test_disconnect_all(self):
        conn1 = gw.sql.open_connection(datafile=self.db_key)
        conn2 = gw.sql.open_connection(datafile="default")
        gw.sql.close_connection(all=True)
        conn3 = gw.sql.open_connection(datafile=self.db_key)
        self.assertIsNot(conn1, conn3)

    # NEW TESTS BELOW


    def test_row_factory_as_dict(self):
        conn = gw.sql.open_connection(datafile=self.db_key, row_factory=True)
        with conn as cursor:
            cursor.execute("CREATE TABLE dict_test (id INTEGER, name TEXT)")
            cursor.execute("INSERT INTO dict_test VALUES (1, 'Zed')")
        rows = gw.sql.execute("SELECT * FROM dict_test")
        self.assertEqual(rows[0]["name"], "Zed")

    def test_infer_type_logic(self):
        self.assertEqual(gw.sql.infer_type("42"), "INTEGER")
        self.assertEqual(gw.sql.infer_type("3.14"), "REAL")
        self.assertEqual(gw.sql.infer_type("hello"), "TEXT")

    def test_load_csv_skips_empty_file(self):
        with open(f"{self.csv_dir}/empty.csv", "w") as f:
            f.write("")  # Create an empty CSV
        conn = gw.sql.open_connection(datafile=self.db_key)
        gw.sql.load_csv(folder=self.csv_dir)
        tables = gw.sql.execute("SELECT name FROM sqlite_master WHERE type='table'")
        table_names = {row[0] for row in tables}
        self.assertIn("sample", table_names)
        self.assertNotIn("empty", table_names)

    def test_duplicate_headers_in_csv(self):
        with open(f"{self.csv_dir}/dups.csv", "w") as f:
            f.write("id,id\n1,2\n3,4")
        conn = gw.sql.open_connection(datafile=self.db_key)
        gw.sql.load_csv(folder=self.csv_dir, force=True)
        rows = gw.sql.execute("SELECT * FROM dups")
        self.assertEqual(len(rows), 2)

    def test_create_and_use_multiple_tables(self):
        conn = gw.sql.open_connection(datafile=self.db_key)
        with conn as cursor:
            cursor.execute("CREATE TABLE a (x INTEGER)")
            cursor.execute("CREATE TABLE b (y TEXT)")
            cursor.execute("INSERT INTO a VALUES (123)")
            cursor.execute("INSERT INTO b VALUES ('abc')")
        ax = gw.sql.execute("SELECT * FROM a")
        by = gw.sql.execute("SELECT * FROM b")
        self.assertEqual(ax[0][0], 123)
        self.assertEqual(by[0][0], "abc")

    def test_force_reload_csv(self):
        conn = gw.sql.open_connection(datafile=self.db_key)
        gw.sql.load_csv(folder=self.csv_dir, force=True)
        with conn as cursor:
            cursor.execute("INSERT INTO sample VALUES (3, 'Charlie')")
        rows_before = gw.sql.execute("SELECT COUNT(*) FROM sample")[0][0]
        gw.sql.load_csv(folder=self.csv_dir, force=True)
        rows_after = gw.sql.execute("SELECT COUNT(*) FROM sample")[0][0]
        self.assertEqual(rows_after, 2)  # Reload resets to original 2 rows

    def test_invalid_sql_engine_raises(self):
        with self.assertRaises(ValueError):
            gw.sql.open_connection(datafile=self.db_key, sql_engine="invalid")

    def test_script_execution_via_resource(self):
        script_path = f"{self.csv_dir}/create_table.sql"
        with open(script_path, "w") as f:
            f.write("CREATE TABLE script_test (id INTEGER);\nINSERT INTO script_test VALUES (99);")
        gw.sql.open_connection(datafile=self.db_key)
        gw.sql.execute(script=script_path)
        rows = gw.sql.execute("SELECT * FROM script_test")
        self.assertEqual(rows, [(99,)])
        os.remove(script_path)


if __name__ == "__main__":
    unittest.main()
