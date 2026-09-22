from gway.install.service import ServiceInstallRecord, ServiceInstallState


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


def test_empty_service_install_state_enumerates_nothing(tmp_path):
    state = ServiceInstallState(tmp_path)

    assert state.projects() == []
    assert state.all() == []
