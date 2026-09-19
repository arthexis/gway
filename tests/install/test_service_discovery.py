from gway import Gateway
import gway.service.discovery as service_discovery


def _service_manifest(name, service="worker"):
    return (
        "[project]\n"
        f"name = {name!r}\n"
        "service_profile_file = '.locks/role.lck'\n"
        "\n"
        f"[services.{service}]\n"
        "command = ['{python}', '-m', 'worker']\n"
        "working_directory = '{project}'\n"
        "profiles = ['Control']\n"
        "restart = 'on-failure'\n"
        "restart_sec = 5\n"
        "\n"
        f"[services.{service}.environment]\n"
        "PYTHONUNBUFFERED = '1'\n"
    )


def test_fresh_gateway_discovers_services_from_managed_project(
    gateway,
    make_project,
    install_environment,
    tmp_path,
    monkeypatch,
):
    source = make_project("arthexis")
    (source / "gway.toml").write_text(
        _service_manifest("arthexis"),
        encoding="utf-8",
    )
    installed = gateway(f"install {source}")

    outside = tmp_path / "outside-services"
    outside.mkdir()
    monkeypatch.chdir(outside)

    fresh = Gateway()

    service = fresh._services[("arthexis", "worker")]
    assert service.project == "arthexis"
    assert service.root == installed.install_path
    assert service.command == ("{python}", "-m", "worker")
    assert service.working_directory == "{project}"
    assert service.profiles == ("Control",)
    assert dict(service.environment) == {"PYTHONUNBUFFERED": "1"}

    catalog = fresh._service_catalogs["arthexis"]
    assert catalog.profile_file == ".locks/role.lck"
    assert catalog.get("worker") is service


def test_service_identity_is_project_scoped(
    gateway,
    make_project,
    install_environment,
    tmp_path,
    monkeypatch,
):
    first = make_project("alpha")
    (first / "gway.toml").write_text(
        _service_manifest("alpha"),
        encoding="utf-8",
    )
    gateway(f"install {first}")

    second = make_project("beta")
    (second / "gway.toml").write_text(
        _service_manifest("beta"),
        encoding="utf-8",
    )
    gateway(f"install {second}")

    outside = tmp_path / "outside-service-identities"
    outside.mkdir()
    monkeypatch.chdir(outside)
    fresh = Gateway()

    assert set(fresh._services) == {
        ("alpha", "worker"),
        ("beta", "worker"),
    }
    assert fresh._services[("alpha", "worker")].root != (
        fresh._services[("beta", "worker")].root
    )


def test_project_without_services_does_not_invoke_service_parser(
    gateway,
    make_project,
    install_environment,
    tmp_path,
    monkeypatch,
):
    source = make_project("wire")
    gateway(f"install {source}")

    calls = []

    def unexpected_load(path):
        calls.append(path)
        raise AssertionError("service parser loaded a manifest without services")

    monkeypatch.setattr(service_discovery, "load", unexpected_load)

    outside = tmp_path / "outside-no-services"
    outside.mkdir()
    monkeypatch.chdir(outside)
    fresh = Gateway()

    assert calls == []
    assert fresh._service_catalogs == {}
    assert fresh._services == {}



def test_service_process_is_manageable_from_fresh_gateway(
    gateway,
    make_project,
    install_environment,
    tmp_path,
    monkeypatch,
):
    source = make_project("arthexis")
    (source / "gway.toml").write_text(
        "[project]\n"
        "name = 'arthexis'\n"
        "\n"
        "[services.sleeper]\n"
        "command = ['{python}', '-c', 'import time; time.sleep(30)']\n"
        "working_directory = '{project}'\n",
        encoding="utf-8",
    )
    gateway(f"install {source}")

    outside = tmp_path / "outside-service-runtime"
    outside.mkdir()
    monkeypatch.chdir(outside)

    first = Gateway()
    started = first("service start arthexis sleeper")
    assert started["running"] is True

    second = Gateway()
    try:
        status = second("service status arthexis sleeper")

        assert status["running"] is True
        assert status["pid"] == started["pid"]

        stopped = second("service stop arthexis sleeper")
        assert stopped["running"] is False
        assert stopped["pid"] is None
    finally:
        first("service stop arthexis sleeper")
