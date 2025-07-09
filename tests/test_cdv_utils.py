import unittest
import importlib.util
from pathlib import Path
import sys
import types


class CDVUtilsTests(unittest.TestCase):
    @staticmethod
    def _load_cdv():
        site_spec = importlib.util.spec_from_file_location(
            "projects.web.site",
            Path(__file__).resolve().parents[1] / "projects" / "web" / "site.py",
        )
        site_mod = importlib.util.module_from_spec(site_spec)
        site_spec.loader.exec_module(site_mod)

        projects_mod = types.ModuleType("projects")
        web_mod = types.ModuleType("projects.web")
        web_mod.site = site_mod
        projects_mod.web = web_mod
        sys.modules.setdefault("projects", projects_mod)
        sys.modules.setdefault("projects.web", web_mod)
        sys.modules.setdefault("projects.web.site", site_mod)

        cdv_path = Path(__file__).resolve().parents[1] / "projects" / "cdv.py"
        spec = importlib.util.spec_from_file_location("cdv_mod", cdv_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    @classmethod
    def setUpClass(cls):
        cls.cdv_mod = cls._load_cdv()
    def test_sanitize_cdv_path(self):
        cases = {
            "foo/bar": "foo/bar",
            "../secret/file.cdv": "secret/file.cdv",
            "foo\\bar": "foo/bar",
            "../../evil": "evil",
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(self.cdv_mod._sanitize_cdv_path(raw), expected)

    def test_parse_and_serialize_roundtrip(self):
        text = "id1:name=John%20Doe:age=30\nid2:msg=Hello"
        records = self.cdv_mod._parse_cdv_text(text)
        self.assertEqual(records, {
            "id1": {"name": "John Doe", "age": "30"},
            "id2": {"msg": "Hello"},
        })
        serialized = self.cdv_mod._records_to_text(records)
        self.assertEqual(serialized, "id1:name=John%20Doe:age=30\nid2:msg=Hello")


if __name__ == "__main__":
    unittest.main()
