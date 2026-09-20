from gway import Gateway
from gway.ingestion.base import find_ingested
from gway.install import Installation, InstallState


def test_fresh_gateway_discovers_managed_user_installation(
    gateway,
    make_project,
    install_environment,
    tmp_path,
    monkeypatch,
):
    source = make_project("wire")
    installed = gateway(f"install {source}")

    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)

    fresh = Gateway()

    assert fresh._installed == {"wire": installed}
    record = find_ingested(fresh, ("wire",))
    assert record is not None
    assert record.value == installed
    assert record.expanded is False
    assert callable(record.expander)


def test_installed_project_expands_project_script_lazily(
    install_environment,
    gateway,
    make_project,
    tmp_path,
    monkeypatch,
):
    source = make_project("tool", launcher=True)
    installed = gateway(f"install {source}")

    outside = tmp_path / "outside-script"
    outside.mkdir()
    monkeypatch.chdir(outside)

    fresh = Gateway()
    record = find_ingested(fresh, ("tool",))
    assert record is not None
    assert record.expanded is False

    result = fresh("tool tool")

    assert result == 0
    assert record.expanded is True
    assert fresh.ops.resolve("tool.tool") is not None
    assert installed.install_path.is_dir()


def test_discovery_skips_stale_or_unsafe_installation_records(
    install_environment,
    tmp_path,
    monkeypatch,
):
    state = InstallState(install_environment.data / "state.sqlite")
    expected = install_environment.data / "projects" / "missing"
    outside = tmp_path / "outside-project"
    outside.mkdir()
    (outside / "pyproject.toml").write_text(
        "[project]\nname = 'outside'\n",
        encoding="utf-8",
    )

    state.put(
        Installation(
            name="missing",
            source="test",
            install_path=expected,
        )
    )
    state.put(
        Installation(
            name="outside",
            source="test",
            install_path=outside,
        )
    )

    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    fresh = Gateway()

    assert fresh._installed == {}
    assert find_ingested(fresh, ("missing",)) is None
    assert find_ingested(fresh, ("outside",)) is None


def test_user_installation_wins_over_system_installation(
    install_environment,
    gateway,
    make_project,
    tmp_path,
    monkeypatch,
):
    system_data = tmp_path / "system-data"
    system_bin = tmp_path / "system-bin"
    monkeypatch.setenv("GWAY_SYSTEM_DATA_DIR", str(system_data))
    monkeypatch.setenv("GWAY_SYSTEM_BIN_DIR", str(system_bin))

    user_source = make_project("shared")
    user = gateway(f"install {user_source}")

    system_source = make_project("shared")
    (system_source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    system = gateway(f"install {system_source} --system")

    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)

    fresh = Gateway()

    assert fresh._installed["shared"] == user
    assert fresh._installed["shared"] != system
    assert find_ingested(fresh, ("shared",)).value == user


def test_uninstall_removes_project_from_future_gateway_bootstrap(
    install_environment,
    gateway,
    make_project,
    tmp_path,
    monkeypatch,
):
    source = make_project("wire")
    installed = gateway(f"install {source}")

    outside = tmp_path / "outside-uninstall"
    outside.mkdir()
    monkeypatch.chdir(outside)

    before = Gateway()
    assert before._installed["wire"] == installed

    removed = gateway("uninstall wire")
    assert removed == installed

    after = Gateway()
    assert "wire" not in after._installed
    assert find_ingested(after, ("wire",)) is None


def test_system_installation_remains_discoverable_after_user_uninstall(
    install_environment,
    gateway,
    make_project,
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("GWAY_SYSTEM_DATA_DIR", str(tmp_path / "system-data"))
    monkeypatch.setenv("GWAY_SYSTEM_BIN_DIR", str(tmp_path / "system-bin"))

    system_source = make_project("shared")
    system = gateway(f"install {system_source} --system")

    user_source = make_project("shared")
    user = gateway(f"install {user_source}")

    outside = tmp_path / "outside-scope-fallback"
    outside.mkdir()
    monkeypatch.chdir(outside)

    before = Gateway()
    assert before._installed["shared"] == user

    gateway("uninstall shared")

    after = Gateway()
    assert after._installed["shared"] == system
    assert find_ingested(after, ("shared",)).value == system
