import sys
from types import ModuleType

import pytest

from gway.ingestion.python import ingest_name


def _install_module(monkeypatch, name):
    module = ModuleType(name)

    def ping():
        return "pong"

    module.ping = ping
    monkeypatch.setitem(sys.modules, name, module)
    return module


def test_ingest_name_imports_and_delegates_to_python_ingestion(monkeypatch, gateway):
    _install_module(monkeypatch, "demo_pkg")

    wrapped = ingest_name(gateway, "demo_pkg")

    assert wrapped
    assert gateway("demo_pkg ping") == "pong"


def test_ingest_name_preserves_fully_qualified_module_root(monkeypatch, gateway):
    _install_module(monkeypatch, "demo_pkg.tools")

    ingest_name(gateway, "demo_pkg.tools")

    assert gateway("demo_pkg tools ping") == "pong"
    assert gateway.ops.resolve("demo_pkg.tools.ping") is not None


def test_ingest_name_allows_explicit_path_override(monkeypatch, gateway):
    _install_module(monkeypatch, "demo_pkg.tools")

    ingest_name(gateway, "demo_pkg.tools", path=("tools",))

    assert gateway("tools ping") == "pong"
    assert gateway.ops.resolve("demo_pkg.tools.ping") is None


def test_ingest_name_rejects_empty_name(gateway):
    with pytest.raises(ValueError, match="non-empty"):
        ingest_name(gateway, "")


def test_ingest_name_propagates_import_errors(gateway):
    with pytest.raises(ModuleNotFoundError):
        ingest_name(gateway, "definitely_missing_gway_test_package")
