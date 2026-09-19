from types import SimpleNamespace

import gway.test as gway_test


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_test_count_counts_definitions_not_parametrized_cases(tmp_path):
    root = tmp_path / "tests"
    _write(
        root / "test_sample.py",
        "import pytest\n"
        "@pytest.mark.parametrize('value', [1, 2, 3])\n"
        "def test_sync(value):\n"
        "    pass\n"
        "async def test_async():\n"
        "    pass\n",
    )

    assert gway_test.count(root=root) == 2


def test_test_summary_groups_top_level_packages_and_root(tmp_path):
    root = tmp_path / "tests"
    _write(root / "test_smoke.py", "def test_root():\n    pass\n")
    _write(
        root / "install" / "test_install.py",
        "def test_one():\n    pass\n"
        "def test_two():\n    pass\n",
    )

    assert gway_test.summary(root=root) == {
        "functions": 3,
        "modules": 2,
        "packages": {"(root)": 1, "install": 2},
    }


def test_test_count_can_filter_and_group_by_package(tmp_path):
    root = tmp_path / "tests"
    _write(root / "install" / "test_install.py", "def test_install():\n    pass\n")
    _write(root / "gateway" / "test_gateway.py", "def test_gateway():\n    pass\n")

    assert gway_test.count("install", root=root) == 1
    assert gway_test.count(root=root, by="package") == {
        "gateway": 1,
        "install": 1,
    }


def test_test_list_reports_function_provenance(tmp_path):
    root = tmp_path / "tests"
    _write(root / "install" / "test_install.py", "def test_install():\n    pass\n")

    assert gway_test.list("install", root=root) == [
        {
            "package": "install",
            "module": "install/test_install.py",
            "name": "test_install",
        }
    ]


def test_test_namespace_is_available_through_gateway(gateway, tmp_path):
    root = tmp_path / "tests"
    _write(root / "install" / "test_install.py", "def test_install():\n    pass\n")

    assert gateway("test count", "install", root=str(root)) == 1
    assert gateway.ops.resolve("test.count") is not None


def test_test_collect_delegates_case_collection_to_pytest(tmp_path, monkeypatch):
    root = tmp_path / "tests"
    root.mkdir()
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return SimpleNamespace(
            stdout="7 tests collected in 0.01s\n",
            stderr="",
            returncode=0,
        )

    monkeypatch.setattr(gway_test._subprocess, "run", fake_run)

    result = gway_test.collect(root=root)

    assert result["collected"] == 7
    assert result["returncode"] == 0
    assert seen["command"][-2:] == ["--collect-only", "-q"]
    assert seen["kwargs"] == {
        "check": False,
        "capture_output": True,
        "text": True,
    }


def test_test_run_translates_gway_options_to_pytest(tmp_path, monkeypatch):
    root = tmp_path / "tests"
    package = root / "install"
    package.mkdir(parents=True)
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return SimpleNamespace(returncode=5)

    monkeypatch.setattr(gway_test._subprocess, "run", fake_run)

    assert (
        gway_test.run(
            "install",
            root=root,
            keyword="mutation",
            failed=True,
            verbose=True,
        )
        == 5
    )
    assert seen["command"][-4:] == ["-k", "mutation", "--lf", "-v"]
    assert seen["kwargs"] == {"check": False}
