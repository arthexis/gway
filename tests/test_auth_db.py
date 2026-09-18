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
        gw.sql.close_db(DB, sql_engine="duckdb", project="auth_db")
        path = gw.resource(DB)
        if os.path.exists(path):
            os.remove(path)

    def test_sync_from_url(self):
        import tempfile
        import http.server
        import socketserver
        import threading

        with tempfile.TemporaryDirectory() as tmp:
            remote_db = os.path.join(tmp, "remote.duckdb")
            local_db = os.path.join(tmp, "local.duckdb")

            uid = gw.auth_db.create_identity("Bob", dbfile=remote_db)
            gw.auth_db.set_basic_auth("bob", "pw", identity_id=uid, dbfile=remote_db)

            gw.sql.close_db(remote_db, sql_engine="duckdb", project="auth_db")

            handler = http.server.SimpleHTTPRequestHandler
            cwd = os.getcwd()
            os.chdir(tmp)
            httpd = socketserver.TCPServer(("127.0.0.1", 0), handler)
            port = httpd.server_address[1]
            thr = threading.Thread(target=httpd.serve_forever, daemon=True)
            thr.start()
            try:
                url = f"http://127.0.0.1:{port}/remote.duckdb"
                gw.auth_db.sync_from_url(url, dbfile=local_db)
            finally:
                httpd.shutdown()
                thr.join()
                os.chdir(cwd)

            ok, ident = gw.auth_db.verify_basic("bob", "pw", dbfile=local_db)
            self.assertTrue(ok)
            self.assertEqual(ident, uid)
            gw.sql.close_db(local_db, sql_engine="duckdb", project="auth_db")

if __name__ == "__main__":
    unittest.main()
