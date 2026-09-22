from gway.install.service import ServiceInstallRecord, ServiceInstallState
from gway.logs import installed_sources


def test_service_install_state_enumerates_projects_and_records(tmp_path):
    state = ServiceInstallState(tmp_path)
    state.put(
        "arthexis",
        [
            ServiceInstallRecord(
                project="arthexis",
                service="web",
                backend_id="arthexis-web.service",
            ),
            ServiceInstallRecord(
                project="arthexis",
                service="worker",
                backend_id="arthexis-worker.service",
            ),
        ],
    )
    state.put(
        "other",
        [
            ServiceInstallRecord(
                project="other",
                service="api",
                backend_id="other-api.service",
            ),
        ],
    )

    assert state.projects() == ["arthexis", "other"]
    assert [(record.project, record.service) for record in state.all()] == [
        ("arthexis", "web"),
        ("arthexis", "worker"),
        ("other", "api"),
    ]


def test_installed_sources_include_project_aggregates_and_services(tmp_path):
    state = ServiceInstallState(tmp_path)
    state.put(
        "arthexis",
        [
            ServiceInstallRecord(
                project="arthexis",
                service="web",
                backend_id="arthexis-web.service",
                backend="systemd",
                system=False,
            ),
            ServiceInstallRecord(
                project="arthexis",
                service="worker",
                backend_id="arthexis-worker.service",
                backend="systemd",
                system=True,
            ),
            ServiceInstallRecord(
                project="arthexis",
                service="beat",
                backend_id="beat",
                backend="process",
                system=False,
            ),
        ],
    )

    sources = installed_sources(state)

    assert [source.identity for source in sources] == [
        "arthexis",
        "arthexis/beat",
        "arthexis/web",
        "arthexis/worker",
    ]

    project = sources[0]
    assert project.kind == "project"
    assert project.project == "arthexis"
    assert project.backend is None

    by_identity = {source.identity: source for source in sources[1:]}
    assert by_identity["arthexis/web"].backend == "systemd"
    assert by_identity["arthexis/web"].backend_id == "arthexis-web.service"
    assert by_identity["arthexis/web"].system is False
    assert by_identity["arthexis/worker"].system is True
    assert by_identity["arthexis/beat"].backend == "process"


def test_installed_sources_do_not_reconstruct_backend_identity(tmp_path):
    state = ServiceInstallState(tmp_path)
    state.put(
        "arthexis",
        [
            ServiceInstallRecord(
                project="arthexis",
                service="web",
                backend_id="custom-unit-name.service",
                backend="systemd",
            )
        ],
    )

    sources = installed_sources(state)
    service = next(source for source in sources if source.kind == "service")

    assert service.identity == "arthexis/web"
    assert service.backend_id == "custom-unit-name.service"


def test_empty_install_state_has_no_installed_sources(tmp_path):
    state = ServiceInstallState(tmp_path)

    assert state.projects() == []
    assert state.all() == []
    assert installed_sources(state) == []
