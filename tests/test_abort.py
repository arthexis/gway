import os
import unittest
from gway import gw

odoo = gw.load_project("odoo")

class AbortTests(unittest.TestCase):
    def test_execute_kw_abort_on_bad_url(self):
        old_url = os.environ.get("ODOO_BASE_URL")
        os.environ["ODOO_BASE_URL"] = "[ODOO_BASE_URL]"
        os.environ.setdefault("ODOO_DB_NAME", "db")
        os.environ.setdefault("ODOO_ADMIN_USER", "user")
        os.environ.setdefault("ODOO_ADMIN_PASSWORD", "pass")
        try:
            with self.assertRaises(SystemExit):
                odoo.execute_kw(model="res.partner", method="read")
        finally:
            if old_url is None:
                os.environ.pop("ODOO_BASE_URL", None)
            else:
                os.environ["ODOO_BASE_URL"] = old_url

if __name__ == "__main__":
    unittest.main()
