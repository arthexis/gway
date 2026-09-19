import pytest

from gway import Gateway
from gway.install.systemd import UnitState


def test_install_singular_service_flag_creates_named_unit(
    tmp_path,
    monkeypatch,
    fake_systemd,
    make_service_project,
    install_environment,
):
    source = make_service_project()
    data = install_environment.data
    monkeypatch.chdir(tmp_path)
    units, calls = fake_systemd

    gateway = Gateway()
    installed = gateway(
        f"install {source} --service web --name custom-web"
    )

    unit = units / "custom-web.service"
    assert installed.name == "demo"
    assert unit.is_file()
    text = unit.read_text(encoding="utf-8")
    assert "WorkingDirectory=" + str(installed.install_path) in text
    assert "Restart=on-failure" in text
    assert "RestartSec=5" in text
    assert (("enable", "custom-web.service"), False, True) in calls

    records = UnitState(data / "systemd").get("demo")
    assert [(record.service, record.unit) for record in records] == [
        ("web", "custom-web.service")
    ]


def test_install_plural_services_flag_creates_multiple_units(
    tmp_path,
    monkeypatch,
    fake_systemd,
    make_service_project,
    install_environment,
):
    source = make_service_project()
    data = install_environment.data
    monkeypatch.chdir(tmp_path)
    units, _ = fake_systemd

    gateway = Gateway()
    gateway(f"install {source} --services web,worker")

    assert (units / "demo-web.service").is_file()
    assert (units / "demo-worker.service").is_file()
    records = UnitState(data / "systemd").get("demo")
    assert [record.service for record in records] == ["web", "worker"]
    assert {record.backend for record in records} == {"systemd"}


def test_explicit_services_converge_owned_unit_set(
    tmp_path,
    monkeypatch,
    fake_systemd,
    make_service_project,
    install_environment,
):
    source = make_service_project()
    data = install_environment.data
    monkeypatch.chdir(tmp_path)
    units, calls = fake_systemd

    gateway = Gateway()
    gateway(f"install {source} --services web,worker")
    gateway(f"install {source} --service web")

    assert (units / "demo-web.service").is_file()
    assert not (units / "demo-worker.service").exists()
    assert (("disable", "--now", "demo-worker.service"), False, False) in calls
    assert [record.service for record in UnitState(data / "systemd").get("demo")] == [
        "web"
    ]


def test_upgrade_preserves_custom_unit_name_without_repeating_flags(
    tmp_path,
    monkeypatch,
    fake_systemd,
    make_service_project,
    install_environment,
):
    source = make_service_project()
    data = install_environment.data
    monkeypatch.chdir(tmp_path)
    units, _ = fake_systemd

    first = Gateway()
    first(f"install {source} --service web --name custom-web")

    manifest = source / "gway.toml"
    manifest.write_text(
        manifest.read_text(encoding="utf-8") + "\n# upgraded\n",
        encoding="utf-8",
    )

    second = Gateway()
    second(f"install {source}")

    assert (units / "custom-web.service").is_file()
    records = UnitState(data / "systemd").get("demo")
    assert [(record.service, record.unit) for record in records] == [
        ("web", "custom-web.service")
    ]


def test_uninstall_removes_all_owned_units(
    tmp_path,
    monkeypatch,
    fake_systemd,
    make_service_project,
    install_environment,
):
    source = make_service_project()
    data = install_environment.data
    monkeypatch.chdir(tmp_path)
    units, calls = fake_systemd

    gateway = Gateway()
    gateway(f"install {source} --services web,worker")
    gateway("uninstall demo")

    assert not (units / "demo-web.service").exists()
    assert not (units / "demo-worker.service").exists()
    assert UnitState(data / "systemd").get("demo") == []
    assert (("disable", "--now", "demo-web.service"), False, False) in calls
    assert (("disable", "--now", "demo-worker.service"), False, False) in calls


def test_unknown_selected_service_fails_before_install_mutation(
    tmp_path,
    monkeypatch,
    fake_systemd,
    make_service_project,
    install_environment,
):
    source = make_service_project()
    data = install_environment.data
    monkeypatch.chdir(tmp_path)

    gateway = Gateway()
    with pytest.raises(ValueError, match="Unknown service"):
        gateway(f"install {source} --service missing")

    assert not (data / "projects" / "demo").exists()



def test_explicit_systemd_backend_matches_default(
    tmp_path,
    monkeypatch,
    fake_systemd,
    make_service_project,
    install_environment,
):
    source = make_service_project()
    data = install_environment.data
    monkeypatch.chdir(tmp_path)
    units, _ = fake_systemd

    gateway = Gateway()
    gateway(f"install {source} --service web --backend systemd")

    assert (units / "demo-web.service").is_file()
    records = UnitState(data / "systemd").get("demo")
    assert [(record.service, record.backend) for record in records] == [
        ("web", "systemd")
    ]


def test_unknown_backend_fails_before_install_mutation(
    tmp_path,
    monkeypatch,
    fake_systemd,
    make_service_project,
    install_environment,
):
    source = make_service_project()
    data = install_environment.data
    monkeypatch.chdir(tmp_path)

    gateway = Gateway()
    with pytest.raises(ValueError, match="Unsupported service backend"):
        gateway(f"install {source} --service web --backend unknown")

    assert not (data / "projects" / "demo").exists()



def test_service_lifecycle_routes_to_systemd_backend(
    tmp_path,
    monkeypatch,
    fake_systemd,
    make_service_project,
    install_environment,
):
    source = make_service_project(
        worker_command="import time; time.sleep(30)",
    )
    monkeypatch.chdir(tmp_path)
    _, calls = fake_systemd

    Gateway()(
        f"install {source} --service worker --backend systemd"
    )

    runtime = Gateway()
    started = runtime("service start demo worker")
    status = runtime("service status demo worker")
    stopped = runtime("service stop demo worker")

    assert started["running"] is True
    assert status["running"] is True
    assert stopped["running"] is False
    assert (("start", "demo-worker.service"), False, True) in calls
    assert (("is-active", "demo-worker.service"), False, False) in calls
    assert (("stop", "demo-worker.service"), False, False) in calls
