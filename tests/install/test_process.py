from gway import Gateway
from gway.install.service import ServiceInstallState
from gway.service.state import ServiceState


def test_process_service_install_persists_without_starting(
    tmp_path,
    monkeypatch,
    install_environment,
):
    monkeypatch.chdir(tmp_path)

    records = Gateway()("service install --backend process sous chef")

    assert [(record.service, record.backend) for record in records] == [
        ("sous-chef", "process")
    ]
    state = ServiceInstallState(
        install_environment.data / "services-installed"
    )
    assert [(item.service, item.backend) for item in state.get("gway")] == [
        ("sous-chef", "process")
    ]
    assert ServiceState(install_environment.data / "services").get(
        "gway",
        "sous-chef",
    ) is None


def test_process_service_lifecycle_works_from_fresh_gateway(
    tmp_path,
    monkeypatch,
    install_environment,
):
    monkeypatch.chdir(tmp_path)
    Gateway()("service install --backend process sous chef")

    first = Gateway()
    started = first("service start sous chef")
    try:
        assert started["running"] is True
        assert isinstance(started["pid"], int)

        second = Gateway()
        status = second("service status sous chef")
        assert status["running"] is True
        assert status["pid"] == started["pid"]

        stopped = second("service stop sous chef")
        assert stopped["running"] is False
    finally:
        first("service stop sous chef")


def test_process_service_install_preserves_other_named_instances(
    tmp_path,
    monkeypatch,
    install_environment,
):
    monkeypatch.chdir(tmp_path)
    runtime = Gateway()

    runtime("service install --backend process --name first sous chef")
    runtime("service install --backend process --name second sous chef")

    state = ServiceInstallState(
        install_environment.data / "services-installed"
    )
    assert [
        (record.service, record.backend)
        for record in state.get("gway")
    ] == [
        ("first", "process"),
        ("second", "process"),
    ]
