import os
import sys
import unittest
import tempfile
import importlib
import warnings
from pathlib import Path
from unittest.mock import patch

from gway.console import normalize_token

try:
    import django  # noqa: F401
except Exception:  # pragma: no cover - depends on optional dependency
    django = None


class ModelProjectTests(unittest.TestCase):
    def setUp(self):
        from gway import gw

        gw._cache.pop("model", None)
        gw._cache.pop("mod", None)

    def test_percent_alias_normalization(self):
        self.assertEqual(normalize_token("%"), "mod")

    @unittest.skipIf(django is None, "django not installed")
    def test_model_project_default_settings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            pkg = tmp_path / "config"
            pkg.mkdir()
            (pkg / "__init__.py").write_text("")
            (pkg / "settings.py").write_text(
                "SECRET_KEY='test'\n"
                "INSTALLED_APPS=['django.contrib.contenttypes']\n"
                "DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}\n"
            )
            sys.path.insert(0, str(tmp_path))
            old_env = os.environ.pop("DJANGO_SETTINGS_MODULE", None)
            try:
                import gway.projects.model as model_proj
                importlib.reload(model_proj)
                from gway import gw

                names = gw.model.list_models()
                self.assertEqual(os.environ["DJANGO_SETTINGS_MODULE"], "config.settings")
                self.assertIn("ContentType", names)
            finally:
                sys.path.remove(str(tmp_path))
                if old_env is not None:
                    os.environ["DJANGO_SETTINGS_MODULE"] = old_env
                else:
                    os.environ.pop("DJANGO_SETTINGS_MODULE", None)

    @unittest.skipIf(django is None, "django not installed")
    def test_model_project_django_lookup(self):
        with patch.dict(os.environ, {"DJANGO_SETTINGS_MODULE": "tests.djproj.settings"}):
            from gway import gw

            mod_proj = gw.model
            names = mod_proj.list_models()
            self.assertTrue({"User", "ContentType"}.issubset(set(names)))
            self.assertIs(mod_proj.user, mod_proj.User)
            self.assertIs(mod_proj.content_type, mod_proj.ContentType)
            self.assertIs(gw.mod.User, mod_proj.User)

    @unittest.skipIf(django is None, "django not installed")
    def test_duplicate_model_warning(self):
        with patch.dict(os.environ, {"DJANGO_SETTINGS_MODULE": "tests.djproj.settings"}):
            from gway import gw
            import gway.projects.model as model_proj

            importlib.reload(model_proj)

            class A:
                __name__ = "Thing"

            class B:
                __name__ = "Thing"

            with patch.object(model_proj.apps, "get_models", lambda: [A, B]):
                with warnings.catch_warnings(record=True) as w:
                    warnings.simplefilter("always")
                    names = gw.model.list_models()

            self.assertTrue(any(item.category is RuntimeWarning for item in w))
            self.assertEqual(names, ["Thing"])
            self.assertIn(gw.model.thing, {A, B})


if __name__ == "__main__":
    unittest.main()

