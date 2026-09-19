import pytest

from gway.sigil import Sigil, Spool


def test_spool_resolves_first_available_sigil(gateway):
    gateway.context["site"] = "MTY"
    spool = Spool("missing", "site")
    assert spool.resolve(gateway) == "MTY"


def test_spool_accepts_existing_sigil_instances(gateway):
    gateway.context["site"] = "MTY"
    sigil = Sigil("site")
    spool = Spool(sigil)
    assert spool[0] is sigil
    assert spool.resolve(gateway) == "MTY"


def test_empty_spool_raises():
    with pytest.raises(KeyError, match="No items"):
        Spool().resolve({})


def test_spool_rejects_unordered_alternatives():
    with pytest.raises(TypeError, match="preserve order"):
        Spool({"site", "fallback"})


def test_spool_only_falls_back_on_resolution_miss():
    class Broken:
        def find_value(self, key, default=None):
            raise RuntimeError("broken source")

    with pytest.raises(RuntimeError, match="broken source"):
        Spool("site", "fallback").resolve(Broken())
