from types import SimpleNamespace

import pytest

from gway import Gateway
from gway.dispatch import CheckError
import gway.install.service.systemd as systemd


def _write_souschef_project(root, *, marker):
    root.mkdir()
    (root / "pyproject.toml").write_text(
        "[project]\n"
        "name = 'demo'\n"
        "\n"
        "[tool.gway.sous-chef.probe]\n"
        "recipe = 'probe.rx'\n"
        "timeout = '5s'\n"
        "\n"
        "[tool.gway.sous-chef.fail]\n"
        "recipe = 'fail.rx'\n"
        "timeout = '5s'\n",
        encoding="utf-8",
    )
    (root / "probe.py").write_text(
        "from pathlib import Path\n"
        f"_marker = Path({str(marker)!r})\n"
        "def mark():\n"
        "    _marker.write_text('ran', encoding='utf-8')\n"
        "    return {'status': 'healthy'}\n",
        encoding="utf-8",
    )
    (root / "probe.rx").write_text("probe mark\n", encoding="utf-8")
    (root / "fail.py").write_text(
        "def explode():\n"
        "    raise RuntimeError('job failed')\n",
        encoding="utf-8",
    )
    (root / "fail.rx").write_text("fail explode\n", encoding="utf-8")
    return root


def _write_deployment_recipes(root, source, destination):
    recipes = root / "recipes"
    recipes.mkdir()
    setup = recipes / "setup.rx"
    verify = recipes / "verify.rx"
    semantic_failure = recipes / "semantic-failure.rx"
    service_failure = recipes / "service-failure.rx"

    verify.write_text(
        "sous chef run probe --project demo\n"
        "check --success true\n",
        encoding="utf-8",
    )
    setup.write_text(
        f"copy {source} --to {destination} --rollback deploy\n"
        "service install --backend systemd sous chef\n"
        "service start sous chef\n"
        "service status sous chef\n"
        "check --running true\n"
        "./verify.rx\n"
        "commit deploy\n",
        encoding="utf-8",
    )
    semantic_failure.write_text(
        f"copy {source} --to {destination} --rollback deploy\n"
        "sous chef run fail --project demo\n"
        "check --success true\n"
        "./verify.rx\n"
        "commit deploy\n",
        encoding="utf-8",
    )
    service_failure.write_text(
        f"copy {source} --to {destination} --rollback deploy\n"
        "service install --backend systemd sous chef\n"
        "service start --timeout 0.01 sous chef\n"
        "./verify.rx\n"
        "commit deploy\n",
        encoding="utf-8",
    )
    return setup, semantic_failure, service_failure


def _runtime_for_project(project, monkeypatch):
    monkeypatch.chdir(project)
    return Gateway()


def test_souschef_recipe_acceptance_crosses_recipe_service_job_and_fresh_runtime(
    tmp_path,
    monkeypatch,
    fake_systemd,
    install_environment,
):
    marker = tmp_path / "job-ran.txt"
    source = tmp_path / "source.txt"
    destination = tmp_path / "deployed.txt"
    source.write_text("configuration", encoding="utf-8")
    project = _write_souschef_project(tmp_path / "project", marker=marker)
    setup, _, _ = _write_deployment_recipes(project, source, destination)

    runtime = _runtime_for_project(project, monkeypatch)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    result = runtime(setup)

    assert result == "deploy"
    assert destination.read_text(encoding="utf-8") == "configuration"
    assert marker.read_text(encoding="utf-8") == "ran"
    assert runtime.journal.get("deploy") is None

    fresh = Gateway()
    assert fresh("service status sous chef")["running"] is True
    assert fresh("service restart sous chef")["running"] is True
    assert fresh("service stop sous chef")["running"] is False
    assert fresh("service start sous chef")["running"] is True


def test_souschef_semantic_job_failure_stops_recipe_and_rolls_back(
    tmp_path,
    monkeypatch,
    fake_systemd,
    install_environment,
):
    marker = tmp_path / "job-ran.txt"
    source = tmp_path / "source.txt"
    destination = tmp_path / "deployed.txt"
    source.write_text("configuration", encoding="utf-8")
    project = _write_souschef_project(tmp_path / "project", marker=marker)
    _, semantic_failure, _ = _write_deployment_recipes(
        project,
        source,
        destination,
    )

    runtime = _runtime_for_project(project, monkeypatch)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    with pytest.raises(CheckError, match="success"):
        runtime(semantic_failure)

    assert not marker.exists()
    assert not destination.exists()
    assert runtime.journal.get("deploy") is None


def test_souschef_service_timeout_stops_recipe_with_operation_identity_and_rollback(
    tmp_path,
    monkeypatch,
    install_environment,
):
    marker = tmp_path / "job-ran.txt"
    source = tmp_path / "source.txt"
    destination = tmp_path / "deployed.txt"
    source.write_text("configuration", encoding="utf-8")
    project = _write_souschef_project(tmp_path / "project", marker=marker)
    _, _, service_failure = _write_deployment_recipes(
        project,
        source,
        destination,
    )

    units = tmp_path / "units"
    monkeypatch.setattr(systemd, "unit_root", lambda **kwargs: units)

    runtime = _runtime_for_project(project, monkeypatch)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)

    def run(operation, *, check=True, timeout=systemd.SYSTEMCTL_TIMEOUT):
        if operation.action == "start" and operation.unit == "gway-sous-chef.service":
            raise systemd._SystemdOperationError(
                operation,
                "sous chef start timed out",
                timeout=timeout,
            )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(systemd, "_run_systemctl_operation", run)

    with pytest.raises(systemd._SystemdOperationError) as raised:
        runtime(service_failure)

    assert raised.value.action == "start"
    assert raised.value.unit == "gway-sous-chef.service"
    assert raised.value.timeout == 0.01
    assert not marker.exists()
    assert not destination.exists()
    assert runtime.journal.get("deploy") is None
