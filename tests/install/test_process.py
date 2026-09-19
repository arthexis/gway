from gway import Gateway
from gway.install.systemd import UnitState
from gway.service.state import ServiceState


def test_process_backend_install_persists_without_starting(
    install_declared_service,
    install_environment,
):
    _, installed = install_declared_service(backend="process")

    records = UnitState(install_environment.data / "systemd").get("demo")
    assert [(record.service, record.backend) for record in records] == [
        ("worker", "process")
    ]
    assert ServiceState(install_environment.data / "services").get(
        "demo",
        "worker",
    ) is None
    assert installed.install_path.is_dir()


def test_process_backend_lifecycle_works_from_fresh_gateway(
    install_declared_service,
    install_environment,
):
    install_declared_service(backend="process")

    first = Gateway()
    started = first("service start demo worker")
    try:
        assert started["running"] is True
        assert isinstance(started["pid"], int)

        second = Gateway()
        status = second("service status demo worker")
        assert status["running"] is True
        assert status["pid"] == started["pid"]

        stopped = second("service stop demo worker")
        assert stopped["running"] is False
        assert stopped["pid"] is None
    finally:
        first("service stop demo worker")


def test_uninstall_stops_running_process_backend_service(
    install_declared_service,
    install_environment,
):
    install_declared_service(backend="process")
    started = Gateway()("service start demo worker")
    assert started["running"] is True

    removed = Gateway()("uninstall demo")

    assert removed.name == "demo"
    assert UnitState(install_environment.data / "systemd").get("demo") == []
    assert ServiceState(install_environment.data / "services").get(
        "demo",
        "worker",
    ) is None


def test_switching_from_systemd_to_process_removes_old_unit(
    fake_systemd,
    install_declared_service,
    install_environment,
):
    units, calls = fake_systemd

    source, _ = install_declared_service(backend="systemd")
    assert (units / "demo-worker.service").is_file()

    Gateway()(f"install {source} --service worker --backend process")

    assert not (units / "demo-worker.service").exists()
    assert (("disable", "--now", "demo-worker.service"), False, False) in calls
    records = UnitState(install_environment.data / "systemd").get("demo")
    assert [(record.service, record.backend) for record in records] == [
        ("worker", "process")
    ]
