import os
import pytest

from gway.console import normalize_token


def test_percent_alias_normalization():
    assert normalize_token("%") == "mod"


def test_model_project_default_settings(monkeypatch, tmp_path):
    django = pytest.importorskip("django")
    pkg = tmp_path / "config"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("")
    (pkg / "settings.py").write_text(
        "SECRET_KEY='test'\n"
        "INSTALLED_APPS=['django.contrib.contenttypes']\n"
        "DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}\n"
    )
    monkeypatch.syspath_prepend(tmp_path)
    monkeypatch.delenv("DJANGO_SETTINGS_MODULE", raising=False)
    import importlib
    import gway.projects.model as model_proj
    importlib.reload(model_proj)
    from gway import gw
    gw._cache.pop("model", None)
    gw._cache.pop("mod", None)
    names = gw.model.list_models()
    assert os.environ["DJANGO_SETTINGS_MODULE"] == "config.settings"
    assert "ContentType" in names


def test_model_project_django_lookup(monkeypatch):
    django = pytest.importorskip("django")
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "tests.djproj.settings")
    from gway import gw

    mod_proj = gw.model
    names = mod_proj.list_models()
    assert {"User", "ContentType"}.issubset(set(names))
    assert mod_proj.user is mod_proj.User
    assert mod_proj.content_type is mod_proj.ContentType
    # alias project
    assert gw.mod.User is mod_proj.User


def test_duplicate_model_warning(monkeypatch):
    django = pytest.importorskip("django")
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "tests.djproj.settings")
    from gway import gw
    import importlib
    import gway.projects.model as model_proj

    # ensure fresh model map and cache
    importlib.reload(model_proj)
    gw._cache.pop("model", None)
    gw._cache.pop("mod", None)

    class A: __name__ = "Thing"
    class B: __name__ = "Thing"

    monkeypatch.setattr(model_proj.apps, "get_models", lambda: [A, B])

    with pytest.warns(RuntimeWarning):
        names = gw.model.list_models()
    assert names == ["Thing"]
    assert gw.model.thing in {A, B}
