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
    assert record.expander is None
    assert fresh.ops.resolve("wire") is None


def test_installed_project_discovery_does_not_eagerly_ingest_django(
    gateway,
    make_project,
    install_environment,
    tmp_path,
    monkeypatch,
    django_ingest_spy,
):
    source = make_project("backend")
    (source / "manage.py").write_text("# django entry\n", encoding="utf-8")
    (source / "gway.toml").write_text(
        "[project]\n"
        "name = 'backend'\n"
        "\n"
        "[ingest]\n"
        "django = '.'\n",
        encoding="utf-8",
    )
    gateway(f"install {source}")

    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)

    fresh = Gateway()

    assert "backend" in fresh._installed
    assert django_ingest_spy == {}
    assert fresh.ops.resolve("backend") is None


def test_discovery_skips_stale_or_unsafe_installation_records(
    install_environment,
    tmp_path,
    monkeypatch,
):
    state = InstallState(install_environment.data / "state.sqlite")
    expected = install_environment.data / "projects" / "missing"
    outside = tmp_path / "outside-project"
    outside.mkdir()
    (outside / "gway.toml").write_text(
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


def test_user_installation_wins_unqualified_name_over_system_installation(
    gateway,
    make_project,
    install_environment,
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
    record = find_ingested(fresh, ("shared",))
    assert record.value == user
