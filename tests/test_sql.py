# tests/test_sql.py

import unittest
import tempfile
import shutil
import os
import threading
import time
from gway import gw

TEMP_DB = "work/test_data.sqlite"

class SqlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Ensure temp database is removed before starting
        if os.path.exists(gw.resource(TEMP_DB)):
            os.remove(gw.resource(TEMP_DB))

    @classmethod
    def tearDownClass(cls):
        # Cleanup test database file
        if os.path.exists(gw.resource(TEMP_DB)):
            os.remove(gw.resource(TEMP_DB))
        # Close all GWAY SQL connections and shutdown writer
        gw.sql.close_connection(all=True)

    def setUp(self):
        # Each test gets a fresh database connection
        self.conn = gw.sql.open_db(TEMP_DB)

    def tearDown(self):
        # Close thread's own connection
        gw.sql.close_connection(TEMP_DB)

    def test_create_and_select(self):
        """Can create table, insert, and select (basic I/O)"""
        gw.sql.execute(
            "CREATE TABLE test_table (id INTEGER PRIMARY KEY, name TEXT)",
            connection=self.conn
        )
        gw.sql.execute(
            "INSERT INTO test_table (name) VALUES ('foo'), ('bar'), ('baz')",
            connection=self.conn
        )
        rows = gw.sql.execute(
            "SELECT id, name FROM test_table ORDER BY id",
            connection=self.conn
        )
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0][1], "foo")
        self.assertEqual(rows[2][1], "baz")

    def test_concurrent_reads(self):
        """Multiple threads can read at the same time."""
        gw.sql.execute(
            "CREATE TABLE readers (id INTEGER PRIMARY KEY, x INT)",
            connection=self.conn
        )
        gw.sql.execute(
            "INSERT INTO readers (x) VALUES (1), (2), (3)",
            connection=self.conn
        )
        results = []

        def read_db():
            c = gw.sql.open_db(TEMP_DB)
            out = gw.sql.execute("SELECT sum(x) FROM readers", connection=c)
            results.append(out[0][0])
            gw.sql.close_connection(TEMP_DB)

        threads = [threading.Thread(target=read_db) for _ in range(5)]
        for t in threads: t.start()
        for t in threads: t.join()
        self.assertTrue(all(r == 6 for r in results))

    def test_concurrent_writes_serialized(self):
        """Concurrent writes are serialized and succeed without error."""
        gw.sql.execute(
            "CREATE TABLE writers (id INTEGER PRIMARY KEY, y INT)",
            connection=self.conn
        )

        def write_db(val):
            c = gw.sql.open_db(TEMP_DB)
            gw.sql.execute(
                "INSERT INTO writers (y) VALUES (?)",
                connection=c, args=(val,)
            )
            gw.sql.close_connection(TEMP_DB)

        threads = [threading.Thread(target=write_db, args=(i,)) for i in range(10)]
        for t in threads: t.start()
        for t in threads: t.join()

        rows = gw.sql.execute("SELECT count(*) FROM writers", connection=self.conn)
        self.assertEqual(rows[0][0], 10)

    def test_load_csv(self):
        """Can load a simple CSV into a table using gw.sql.load_csv."""
        # Write a temp CSV file
        tmpdir = tempfile.mkdtemp()
        try:
            csv_path = os.path.join(tmpdir, "data1.csv")
            with open(csv_path, "w", encoding="utf-8") as f:
                f.write("a,b\n1,hello\n2,world\n3,bye\n")
            # Call load_csv
            gw.sql.load_csv(connection=self.conn, folder=tmpdir)
            rows = gw.sql.execute("SELECT * FROM data1 ORDER BY a", connection=self.conn)
            self.assertEqual(len(rows), 3)
            self.assertEqual(rows[1][1], "world")
        finally:
            shutil.rmtree(tmpdir)

    def test_load_excel(self):
        """Can load an Excel workbook with multiple sheets."""
        tmpdir = tempfile.mkdtemp()
        try:
            xls_path = os.path.join(tmpdir, "data.xlsx")
            import pandas as pd
            with pd.ExcelWriter(xls_path) as writer:
                pd.DataFrame({"a": [1, 2]}).to_excel(writer, sheet_name="s1", index=False)
                pd.DataFrame({"b": ["x", "y"]}).to_excel(writer, sheet_name="s2", index=False)

            gw.sql.load_excel(connection=self.conn, file=xls_path)

            rows1 = gw.sql.execute("SELECT * FROM data_s1 ORDER BY a", connection=self.conn)
            rows2 = gw.sql.execute("SELECT * FROM data_s2 ORDER BY b", connection=self.conn)

            self.assertEqual(len(rows1), 2)
            self.assertEqual(rows2[1][0], "y")
        finally:
            shutil.rmtree(tmpdir)

    def test_load_cdv(self):
        """Load a CDV file into a table."""
        tmpdir = tempfile.mkdtemp()
        try:
            path = os.path.join(tmpdir, "vals.cdv")
            with open(path, "w", encoding="utf-8") as f:
                f.write("a:name=foo:age=1\n")
                f.write("b:name=bar:age=2:extra=ok\n")

            gw.sql.load_cdv(connection=self.conn, file=path)

            rows = gw.sql.execute(
                "SELECT id, name, age, extra FROM vals ORDER BY id",
                connection=self.conn,
            )

            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][1], "foo")
            self.assertEqual(rows[1][3], "ok")
        finally:
            shutil.rmtree(tmpdir)

    def test_execute_script(self):
        """Can run an SQL script via execute()."""
        script_path = gw.resource("test_script.sql")
        # Write a small script file
        with open(script_path, "w", encoding="utf-8") as f:
            f.write("CREATE TABLE s1 (x INT); INSERT INTO s1 VALUES (42);")
        try:
            with open(script_path, encoding="utf-8") as f:
                script_text = f.read()
            gw.sql.execute(script_text, connection=self.conn)
            rows = gw.sql.execute("SELECT x FROM s1", connection=self.conn)
            self.assertEqual(rows[0][0], 42)
        finally:
            if os.path.exists(script_path):
                os.remove(script_path)

    def test_infer_type(self):
        """infer_type picks up correct SQLite types"""
        self.assertEqual(gw.sql.infer_type("42"), "INTEGER")
        self.assertEqual(gw.sql.infer_type("3.1415"), "REAL")
        self.assertEqual(gw.sql.infer_type("hello"), "TEXT")

    def test_row_factory(self):
        """Can get dict-like rows using row_factory option."""
        gw.sql.close_connection(all=True)  # Ensure fresh conn
        conn = gw.sql.open_db(TEMP_DB, row_factory=True)
        gw.sql.execute(
            "CREATE TABLE rf (k INT, v TEXT)",
            connection=conn
        )
        gw.sql.execute(
            "INSERT INTO rf VALUES (1, 'x')",
            connection=conn
        )
        rows = gw.sql.execute("SELECT * FROM rf", connection=conn)
        self.assertTrue(hasattr(rows[0], "keys"))
        self.assertEqual(rows[0]["v"], "x")
        gw.sql.close_connection(TEMP_DB)

    def test_invalid_sql_raises(self):
        """Invalid SQL raises an error (and rolls back write)."""
        gw.sql.execute(
            "CREATE TABLE errtest (z INT)", connection=self.conn
        )
        with self.assertRaises(Exception):
            gw.sql.execute("INSRT INTO errtest VALUES (9)", connection=self.conn)
        # Table should be empty
        rows = gw.sql.execute("SELECT count(*) FROM errtest", connection=self.conn)
        self.assertEqual(rows[0][0], 0)

    def test_open_db_invalid_path_message(self):
        """open_db aborts with helpful message on invalid path."""
        bad_dir = "work/bad_db"
        full = gw.resource(bad_dir, dir=True)
        from unittest.mock import patch
        with patch.object(gw, "abort", side_effect=SystemExit(13)) as abort_fn:
            with self.assertRaises(SystemExit):
                gw.sql.open_db(bad_dir)
        abort_msg = abort_fn.call_args[0][0]
        self.assertIn(str(full), abort_msg)
        self.assertIn("permission", abort_msg.lower())

    def test_close_all_connections(self):
        """close_connection(all=True) closes all and stops writer."""
        c1 = gw.sql.open_db(TEMP_DB)
        c2 = gw.sql.open_db(TEMP_DB)
        gw.sql.close_connection(all=True)
        # New connection after all closed should work
        c3 = gw.sql.open_db(TEMP_DB)
        gw.sql.execute("CREATE TABLE foo (id INT)", connection=c3)
        gw.sql.close_connection(TEMP_DB)

    def test_parse_log(self):
        """parse_log tail-inserts matching log lines into a table."""
        log_path = gw.resource("work/test.log")
        if os.path.exists(log_path):
            os.remove(log_path)
        # create empty file
        with open(log_path, "w", encoding="utf-8"):
            pass

        stop_event = threading.Event()
        t = threading.Thread(
            target=gw.sql.parse_log,
            args=(r"(?P<level>\w+): (?P<msg>.+)", log_path),
            kwargs=dict(
                table="log_table",
                connection=self.conn,
                start_at_end=False,
                poll_interval=0.1,
                stop_event=stop_event,
            ),
            daemon=True,
        )
        t.start()

        with open(log_path, "a", encoding="utf-8") as f:
            f.write("INFO: hello\n")
            f.flush()

        time.sleep(0.3)
        stop_event.set()
        t.join(1)

        rows = gw.sql.execute(
            "SELECT level, msg FROM log_table", connection=self.conn
        )
        self.assertEqual(rows[0][0], "INFO")
        self.assertEqual(rows[0][1], "hello")

        os.remove(log_path)

    def test_open_db_persists_params(self):
        """open_db() without args reuses last params."""
        gw.sql.close_connection(all=True)
        c1 = gw.sql.open_db("work/persist.sqlite")
        c2 = gw.sql.open_db()
        self.assertIs(c1, c2)
        gw.sql.close_connection("work/persist.sqlite")

    def test_parse_log_default_mask(self):
        """Default mask parses standard GWay log lines."""
        log_path = gw.resource("work/test_gw.log")
        if os.path.exists(log_path):
            os.remove(log_path)
        with open(log_path, "w", encoding="utf-8"):
            pass

        stop_event = threading.Event()
        t = threading.Thread(
            target=gw.sql.parse_log,
            kwargs=dict(
                log_location=log_path,
                table="gw_log_table",
                connection=self.conn,
                start_at_end=False,
                poll_interval=0.1,
                stop_event=stop_event,
            ),
            daemon=True,
        )
        t.start()

        sample = "12:34:56 INFO [gw:abcd:1234] func foo.py:10  # hi\n"
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(sample)
            f.flush()

        time.sleep(0.3)
        stop_event.set()
        t.join(1)

        rows = gw.sql.execute(
            "SELECT time, level, name, func, file, line, msg FROM gw_log_table",
            connection=self.conn,
        )
        self.assertEqual(rows[0][0], "12:34:56")
        self.assertEqual(rows[0][-1], "hi")

        os.remove(log_path)

if __name__ == "__main__":
    unittest.main()
