import sys

import pytest

from gway.ingestion.python import ingest_path


def test_ingest_module_file(gateway, tmp_path):
    module = tmp_path / "sample.py"
    module.write_text(
        "def ping():\n"
        "    return 'pong'\n"
    )

    ingest_path(gateway, module)

    assert gateway("sample ping") == "pong"


def test_ingest_module_file_with_explicit_module_name(gateway, tmp_path):
    module = tmp_path / "sample.py"
    module.write_text(
        "def ping():\n"
        "    return 'pong'\n"
    )

    ingest_path(gateway, module, name="tools.sample")

    assert gateway("tools sample ping") == "pong"


def test_ingest_module_file_can_reroot_registered_path(gateway, tmp_path):
    module = tmp_path / "sample.py"
    module.write_text(
        "def ping():\n"
        "    return 'pong'\n"
    )

    ingest_path(gateway, module, root=("tools",))

    assert gateway("tools ping") == "pong"
    assert gateway.ops.resolve("sample.ping") is None


def test_ingest_package_directory(gateway, tmp_path):
    package = tmp_path / "demo_pkg"
    package.mkdir()
    (package / "__init__.py").write_text(
        "def ping():\n"
        "    return 'pong'\n"
    )

    ingest_path(gateway, package)

    assert gateway("demo_pkg ping") == "pong"


def test_package_relative_imports_work(gateway, tmp_path):
    package = tmp_path / "demo_pkg"
    package.mkdir()
    (package / "helper.py").write_text(
        "def value():\n"
        "    return 'ok'\n"
    )
    (package / "__init__.py").write_text(
        "from .helper import value\n"
    )

    ingest_path(gateway, package)

    assert gateway("demo_pkg value") == "ok"


def test_ingest_path_rejects_non_python_file(gateway, tmp_path):
    data = tmp_path / "data.txt"
    data.write_text("x")

    with pytest.raises(ValueError, match="Unsupported Python path"):
        ingest_path(gateway, data)


def test_ingest_path_rejects_directory_without_package_init(gateway, tmp_path):
    directory = tmp_path / "plain"
    directory.mkdir()

    with pytest.raises(ValueError, match="no __init__.py"):
        ingest_path(gateway, directory)


def test_failed_import_does_not_leave_new_module_in_sys_modules(gateway, tmp_path):
    module = tmp_path / "broken.py"
    module.write_text("raise RuntimeError('boom')\n")

    sys.modules.pop("broken", None)

    with pytest.raises(RuntimeError, match="boom"):
        ingest_path(gateway, module)

    assert "broken" not in sys.modules
