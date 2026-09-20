import os
import sys
import time
from types import SimpleNamespace

from gway.service.runtime import ProcessBackend
from gway.service.state import ProcessRecord, ServiceState, process_token


def test_process_backend_resolves_project_python_and_cwd(
    tmp_path,
    service_factory,
):
    output = tmp_path / "service-output.txt"
    script = tmp_path / "write_cwd.py"
    script.write_text(
        "import os, pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text(os.getcwd(), encoding='utf-8')\n",
        encoding="utf-8",
    )
    service = service_factory(
        "writer",
        command=(
            "{python}",
            str(script),
            str(output),
        ),
        working_directory="{project}",
        restart="no",
    )
    backend = ProcessBackend(state_root=tmp_path / "state")

    started = backend.start(service)
    assert started["project"] == "demo"
    assert started["service"] == "writer"

    deadline = time.time() + 5
    while time.time() < deadline and not output.exists():
        time.sleep(0.01)

    assert output.exists()
    assert output.read_text(encoding="utf-8") == str(tmp_path.resolve())

    deadline = time.time() + 5
    status = backend.status(service)
    while time.time() < deadline and status["running"]:
        time.sleep(0.01)
        status = backend.status(service)

    assert status["running"] is False


def test_process_backend_start_is_idempotent_while_running(tmp_path, service_factory):
    service = service_factory()
    backend = ProcessBackend(state_root=tmp_path / "state")

    first = backend.start(service)
    try:
        second = backend.start(service)

        assert first["running"] is True
        assert second["running"] is True
        assert second["pid"] == first["pid"]
    finally:
        backend.stop(service)


def test_process_backend_restart_replaces_process(tmp_path, service_factory):
    service = service_factory()
    backend = ProcessBackend(state_root=tmp_path / "state")

    first = backend.start(service)
    try:
        restarted = backend.restart(service)

        assert restarted["running"] is True
        assert restarted["pid"] != first["pid"]
    finally:
        backend.stop(service)


def test_durable_state_allows_later_backend_to_manage_service(
    tmp_path, service_factory
):
    service = service_factory()
    state_root = tmp_path / "state"
    starter = ProcessBackend(state_root=state_root)
    later = ProcessBackend(state_root=state_root)

    started = starter.start(service)
    try:
        status = later.status(service)

        assert status["running"] is True
        assert status["pid"] == started["pid"]
        assert status["started_at"] == started["started_at"]

        stopped = later.stop(service)
        assert stopped["running"] is False
        assert stopped["pid"] is None
        assert ServiceState(state_root).get("demo", "sleeper") is None
    finally:
        starter.stop(service)


def test_stale_pid_record_is_removed_without_signalling_unowned_process(
    tmp_path,
    monkeypatch,
    service_factory,
):
    service = service_factory(
        "stale",
        command=("{python}", "-c", "pass"),
    )
    state_root = tmp_path / "state"
    state = ServiceState(state_root)
    state.put(
        ProcessRecord(
            project="demo",
            service="stale",
            pid=os.getpid(),
            process_token="not-the-current-token",
            command=(sys.executable,),
            cwd=str(tmp_path),
            started_at="2026-01-01T00:00:00+00:00",
        )
    )
    signals = []
    original_kill = os.kill

    def guarded_kill(pid, sig):
        if sig != 0:
            signals.append((pid, sig))
        return original_kill(pid, sig)

    monkeypatch.setattr(os, "kill", guarded_kill)
    backend = ProcessBackend(state_root=state_root)

    stopped = backend.stop(service)

    assert stopped["running"] is False
    assert signals == []
    assert state.get("demo", "stale") is None


def test_process_record_uses_kernel_start_token_when_available(
    tmp_path, service_factory
):
    service = service_factory()
    backend = ProcessBackend(state_root=tmp_path / "state")

    backend.start(service)
    try:
        record = ServiceState(tmp_path / "state").get("demo", "sleeper")
        assert record is not None
        if process_token(record.pid) is not None:
            assert record.process_token == process_token(record.pid)
    finally:
        backend.stop(service)


def test_running_service_reports_stale_after_installation_fingerprint_changes(
    tmp_path,
    service_factory,
):
    service = service_factory()
    installations = {
        "demo": SimpleNamespace(fingerprint="first"),
    }
    backend = ProcessBackend(
        state_root=tmp_path / "state",
        installations=installations,
    )

    started = backend.start(service)
    try:
        assert started["stale"] is False

        installations["demo"] = SimpleNamespace(fingerprint="second")
        status = backend.status(service)

        assert status["running"] is True
        assert status["pid"] == started["pid"]
        assert status["stale"] is True
    finally:
        backend.stop(service)
