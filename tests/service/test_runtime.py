import os
import sys
import time

from gway.service.model import Service
from gway.service.runtime import ProcessBackend


def test_process_backend_resolves_project_python_cwd_and_environment(tmp_path):
    output = tmp_path / "service-output.txt"
    script = tmp_path / "write_env.py"
    script.write_text(
        "import os, pathlib, sys\n"
        "pathlib.Path(sys.argv[1]).write_text("
        "os.getcwd() + '\\n' + os.environ['SERVICE_VALUE'], encoding='utf-8')\n",
        encoding="utf-8",
    )
    service = Service(
        project="demo",
        name="writer",
        root=tmp_path,
        command=(
            "{python}",
            str(script),
            str(output),
        ),
        working_directory="{project}",
        environment={"SERVICE_VALUE": "{project}/value"},
    )
    backend = ProcessBackend()

    started = backend.start(service)
    assert started["project"] == "demo"
    assert started["service"] == "writer"
    assert started["running"] is True
    assert isinstance(started["pid"], int)

    deadline = time.time() + 5
    while time.time() < deadline and not output.exists():
        time.sleep(0.01)

    assert output.exists()
    cwd, value = output.read_text(encoding="utf-8").splitlines()
    assert cwd == str(tmp_path.resolve())
    assert value == str((tmp_path / "value").resolve())

    status = backend.status(service)
    assert status["running"] is False
    assert status["pid"] is None


def test_process_backend_start_is_idempotent_while_running(tmp_path):
    service = Service(
        project="demo",
        name="sleeper",
        root=tmp_path,
        command=("{python}", "-c", "import time; time.sleep(30)"),
    )
    backend = ProcessBackend()

    first = backend.start(service)
    try:
        second = backend.start(service)

        assert first["running"] is True
        assert second["running"] is True
        assert second["pid"] == first["pid"]
    finally:
        backend.stop(service)


def test_process_backend_restart_replaces_process(tmp_path):
    service = Service(
        project="demo",
        name="sleeper",
        root=tmp_path,
        command=("{python}", "-c", "import time; time.sleep(30)"),
    )
    backend = ProcessBackend()

    first = backend.start(service)
    try:
        restarted = backend.restart(service)

        assert restarted["running"] is True
        assert restarted["pid"] != first["pid"]
    finally:
        backend.stop(service)
