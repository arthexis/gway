from gway import Gateway


def fresh_gateway(tmp_path, monkeypatch):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / ".gway-data"))
    monkeypatch.chdir(tmp_path)
    return Gateway()


def test_sous_chef_list_and_inspect_local_jobs(tmp_path, monkeypatch, souschef_project):
    souschef_project(tmp_path)
    gateway = fresh_gateway(tmp_path, monkeypatch)

    listed = gateway("sous chef list")
    inspected = gateway("sous chef inspect cleanup")

    assert listed == [
        {
            "project": "demo",
            "job": "cleanup",
            "recipe": str((tmp_path / "cleanup.rx").resolve()),
            "triggers": ["every"],
            "timeout": 300.0,
        }
    ]
    assert inspected["project"] == "demo"
    assert inspected["job"] == "cleanup"
    assert inspected["every"] == 3600.0
    assert inspected["timeout"] == 300.0


def test_sous_chef_run_executes_job_through_scheduler(
    tmp_path, monkeypatch, souschef_project
):
    souschef_project(tmp_path)
    gateway = fresh_gateway(tmp_path, monkeypatch)

    result = gateway("sous chef run cleanup")

    assert result == {
        "project": "demo",
        "job": "cleanup",
        "success": True,
        "reasons": ["manual"],
        "value": "clean",
        "error": None,
    }


def test_multiword_sous_chef_path_wins_over_sous_operation(
    tmp_path, monkeypatch, souschef_project
):
    souschef_project(tmp_path)
    gateway = fresh_gateway(tmp_path, monkeypatch)

    gateway.wrap("sous", lambda chef: f"fallback:{chef}")

    listed = gateway("sous chef list")

    assert listed[0]["job"] == "cleanup"
    assert listed[0]["project"] == "demo"


def test_builtin_sous_chef_service_preset_targets_package_entrypoint(
    tmp_path,
    monkeypatch,
):
    gateway = fresh_gateway(tmp_path, monkeypatch)

    service = gateway("service inspect sous chef")

    assert service["project"] == "gway"
    assert service["service"] == "sous-chef"
    assert service["description"] == "Gway single-worker recipe scheduler"
    assert service["launchable"] == {
        "name": "sous.chef",
        "kind": "operation",
        "command": [
            "{python}",
            "-m",
            "gway",
            "sous",
            "chef",
        ],
    }
    assert service["working_directory"] == "{project}"
    assert service["restart"] == "on-failure"
    assert service["attempts"] == 3
    assert service["restart_sec"] == 5.0


def test_builtin_service_uses_gway_data_for_runtime_state(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("GWAY_DATA_DIR", str(data))
    monkeypatch.chdir(tmp_path)

    gateway = Gateway()
    service = gateway._service_presets[("gway", "sous-chef")]

    assert service.state_root == (data / "services").resolve()
