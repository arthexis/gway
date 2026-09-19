from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

import gway.ingestion.python as python_ingestor
import gway.ingestion.proc as proc_ingestor
from gway.ingestion import ingest, ingest_path


def test_ingest_routes_imported_python_object(monkeypatch, gateway):
    source = SimpleNamespace()
    seen = {}

    def fake(runtime, value, **kwargs):
        seen["runtime"] = runtime
        seen["value"] = value
        return "python-object"

    monkeypatch.setattr(python_ingestor, "ingest_python", fake)

    assert ingest(gateway, source) == "python-object"
    assert seen == {"runtime": gateway, "value": source}


def test_ingest_routes_fully_qualified_name_to_python(monkeypatch, gateway):
    seen = {}

    def fake(runtime, name, **kwargs):
        seen["name"] = name
        return "python-name"

    monkeypatch.setattr(python_ingestor, "ingest_name", fake)

    assert ingest(gateway, "package.module") == "python-name"
    assert seen["name"] == "package.module"


def test_ingest_routes_python_file_path(monkeypatch, gateway, tmp_path):
    module = tmp_path / "sample.py"
    module.write_text("VALUE = 1\n")
    seen = {}

    def fake(runtime, path, **kwargs):
        seen["path"] = path
        return "python-path"

    monkeypatch.setattr(python_ingestor, "ingest_path", fake)

    assert ingest(gateway, module) == "python-path"
    assert seen["path"] == module


def test_ingest_path_routes_package_directory_to_python(monkeypatch, gateway, tmp_path):
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "__init__.py").write_text("")
    seen = {}

    def fake(runtime, path, **kwargs):
        seen["path"] = path
        return "python-package"

    monkeypatch.setattr(python_ingestor, "ingest_path", fake)

    assert ingest_path(gateway, package) == "python-package"
    assert seen["path"] == package


def test_ingest_path_routes_executable_to_proc(monkeypatch, gateway, tmp_path):
    executable = tmp_path / "systemctl"
    executable.write_text("#!/bin/sh\n")
    executable.chmod(0o755)
    seen = {}

    def fake(runtime, path, **kwargs):
        seen["path"] = path
        return "proc-path"

    monkeypatch.setattr(proc_ingestor, "ingest_path", fake)

    assert ingest_path(gateway, executable) == "proc-path"
    assert seen["path"] == executable


def test_gateway_exposes_ingestion_entry_points(gateway, monkeypatch):
    module = SimpleNamespace()
    monkeypatch.setattr(python_ingestor, "ingest_python", lambda runtime, source, **kwargs: source)

    assert gateway.ingest(module) is module


def test_unknown_non_python_non_executable_path_is_rejected(gateway, tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("data")

    with pytest.raises(ValueError, match="Unsupported ingestion path"):
        gateway.ingest_path(path)


def test_ingest_routes_imported_module_to_module_ingestion(monkeypatch, gateway):
    module = ModuleType("demo")
    seen = {}

    def fake(runtime, value, **kwargs):
        seen["runtime"] = runtime
        seen["value"] = value
        return "python-module"

    monkeypatch.setattr(python_ingestor, "ingest_module", fake)

    assert ingest(gateway, module) == "python-module"
    assert seen == {"runtime": gateway, "value": module}


def test_ingest_routes_bare_existing_filename_to_path(monkeypatch, gateway, tmp_path):
    source = tmp_path / "README"
    source.write_text("hello\n")
    seen = {}

    def fake(runtime, path, **kwargs):
        seen["path"] = path
        return "filesystem"

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("gway.ingestion.router.ingest_path", fake)

    assert ingest(gateway, "README") == "filesystem"
    assert seen["path"] == "README"


def test_ingest_routes_relative_path_syntax_without_requiring_existence(
    monkeypatch,
    gateway,
):
    seen = {}

    def fake(runtime, path, **kwargs):
        seen["path"] = path
        return "filesystem"

    monkeypatch.setattr("gway.ingestion.router.ingest_path", fake)

    assert ingest(gateway, "folder/README") == "filesystem"
    assert seen["path"] == "folder/README"


def test_ingest_routes_relative_path_object_even_without_separator(
    monkeypatch,
    gateway,
):
    seen = {}

    def fake(runtime, path, **kwargs):
        seen["path"] = path
        return "filesystem"

    monkeypatch.setattr("gway.ingestion.router.ingest_path", fake)

    source = Path("README")
    assert ingest(gateway, source) == "filesystem"
    assert seen["path"] == source


def test_ingest_bare_missing_name_remains_python_import(monkeypatch, gateway):
    seen = {}

    def fake(runtime, name, **kwargs):
        seen["name"] = name
        return "python-name"

    monkeypatch.setattr(python_ingestor, "ingest_name", fake)

    assert ingest(gateway, "definitely_missing_local_entry") == "python-name"
    assert seen["name"] == "definitely_missing_local_entry"


def test_direct_command_resolution_does_not_discover_same_named_file(
    gateway,
    tmp_path,
    monkeypatch,
):
    source = tmp_path / "README"
    source.write_text("ignored\n")
    monkeypatch.chdir(tmp_path)

    with pytest.raises(LookupError):
        gateway("README")
