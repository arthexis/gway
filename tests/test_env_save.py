import os
import unittest
from pathlib import Path
from gway import gw


class EnvSaveTests(unittest.TestCase):
    def setUp(self):
        client = os.environ.get("CLIENT") or "root"
        self.env_file = Path(gw.base_path) / "envs" / "clients" / f"{client.lower()}.env"
        self.env_file.parent.mkdir(parents=True, exist_ok=True)
        self.original = self.env_file.read_text() if self.env_file.exists() else ""
        for var in ("TEST_VAR", "FOO", "BAR"):
            os.environ.pop(var, None)

    def tearDown(self):
        self.env_file.write_text(self.original)
        for var in ("TEST_VAR", "FOO", "BAR"):
            os.environ.pop(var, None)

    def test_save_positional(self):
        gw.env.save("TEST_VAR", "123")
        contents = self.env_file.read_text()
        self.assertIn("TEST_VAR=123", contents)
        self.assertEqual(os.environ.get("TEST_VAR"), "123")

    def test_save_kwarg(self):
        gw.env.save(test_var="456")
        contents = self.env_file.read_text()
        self.assertIn("TEST_VAR=456", contents)
        self.assertEqual(os.environ.get("TEST_VAR"), "456")

    def test_normalizes_existing_keys(self):
        self.env_file.write_text("foo=1\n")
        gw.env.save("bar", "2")
        contents = self.env_file.read_text()
        self.assertIn("FOO=1", contents)
        self.assertIn("BAR=2", contents)
        self.assertNotIn("foo=1", contents)


if __name__ == "__main__":
    unittest.main()
