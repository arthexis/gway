import pytest

from gway.install import InstallState


def _project(tmp_path, name="demo"):
    root = tmp_path / "source" / name
    root.mkdir(parents=True)
    (root / "gway.toml").write_text(
        f"[project]\nname = {name!r}\n",
        encoding="utf-8",
    )
    (root / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    return root


def test_install_builtin_installs_local_project(gateway, tmp_path, monkeypatch):
    source = _project(tmp_path, "wire")
    data = tmp_path / "data"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data))

    installed = gateway(f"install {source}")

    assert installed.name == "wire"
    assert installed.scope == "user"
    assert installed.install_path == (data / "projects" / "wire").resolve()
    assert (installed.install_path / "module.py").is_file()
    assert InstallState(data / "state.sqlite").get("wire") == installed


def test_install_builtin_reconciles_changed_source_by_default(
    gateway,
    tmp_path,
    monkeypatch,
):
    source = _project(tmp_path, "wire")
    data = tmp_path / "data"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data))

    first = gateway(f"install {source}")
    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")

    second = gateway(f"install {source}")

    assert second.fingerprint != first.fingerprint
    assert (second.install_path / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_install_builtin_defaults_upgrade_on_but_no_upgrade_can_suppress_change(
    gateway,
    tmp_path,
    monkeypatch,
):
    source = _project(tmp_path, "wire")
    data = tmp_path / "data"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data))

    first = gateway(f"install {source}")
    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    second = gateway(f"install {source} --no-upgrade")

    assert second == first
    assert (first.install_path / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"


def test_install_builtin_ref_is_reserved_for_future_git_sources(
    gateway,
    tmp_path,
    monkeypatch,
):
    source = _project(tmp_path, "wire")
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))

    with pytest.raises(ValueError, match="not supported for local"):
        gateway(f"install {source} --ref gateway-rebuild")


def test_install_builtin_rejects_force_with_stash(gateway):
    with pytest.raises(ValueError, match="mutually exclusive"):
        gateway("install arthexis/gway --force --stash")


def test_install_builtin_supports_system_scope(gateway, tmp_path, monkeypatch):
    source = _project(tmp_path, "wire")
    data = tmp_path / "system-data"
    monkeypatch.setenv("GWAY_SYSTEM_DATA_DIR", str(data))

    installed = gateway(f"install {source} --system")

    assert installed.scope == "system"
    assert installed.install_path == (data / "projects" / "wire").resolve()


def test_uninstall_builtin_removes_managed_project(gateway, tmp_path, monkeypatch):
    source = _project(tmp_path, "wire")
    data = tmp_path / "data"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data))

    installed = gateway(f"install {source}")
    removed = gateway("uninstall wire")

    assert removed == installed
    assert not installed.install_path.exists()
    assert InstallState(data / "state.sqlite").get("wire") is None


def test_uninstall_builtin_is_idempotent(gateway, tmp_path, monkeypatch):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))

    assert gateway("uninstall missing") is None



def test_install_builtin_refuses_dirty_managed_copy_by_default(
    gateway,
    tmp_path,
    monkeypatch,
):
    source = _project(tmp_path, "wire")
    data = tmp_path / "data"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data))
    installed = gateway(f"install {source}")
    managed = installed.install_path / "module.py"
    managed.write_text("CUSTOM = True\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="local modifications"):
        gateway(f"install {source}")

    assert managed.read_text(encoding="utf-8") == "CUSTOM = True\n"


def test_install_builtin_force_repairs_dirty_managed_copy(
    gateway,
    tmp_path,
    monkeypatch,
):
    source = _project(tmp_path, "wire")
    data = tmp_path / "data"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data))
    installed = gateway(f"install {source}")
    managed = installed.install_path / "module.py"
    managed.write_text("CUSTOM = True\n", encoding="utf-8")

    gateway(f"install {source} --force")

    assert managed.read_text(encoding="utf-8") == "VALUE = 1\n"
    assert not (data / "stashes").exists()


def test_install_builtin_stash_preserves_dirty_managed_copy(
    gateway,
    tmp_path,
    monkeypatch,
):
    source = _project(tmp_path, "wire")
    data = tmp_path / "data"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data))
    installed = gateway(f"install {source}")
    managed = installed.install_path / "module.py"
    managed.write_text("CUSTOM = True\n", encoding="utf-8")

    gateway(f"install {source} --stash")

    stashes = list((data / "stashes" / "wire").iterdir())
    assert len(stashes) == 1
    assert (stashes[0] / "tree" / "module.py").read_text(
        encoding="utf-8"
    ) == "CUSTOM = True\n"
    assert managed.read_text(encoding="utf-8") == "VALUE = 1\n"
