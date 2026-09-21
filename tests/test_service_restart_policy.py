from gway.gateway import Gateway
from gway.install.service.systemd import render
from gway.launchable import Launchable
from gway.service.model import Service
from gway.service.runtime import ProcessBackend


def service(tmp_path, **policy):
    launchable = Launchable.operation("demo.worker", root=tmp_path)
    return Service.from_launchable(
        "demo",
        "worker",
        tmp_path,
        launchable,
        **policy,
    )


def test_service_restart_defaults(tmp_path):
    definition = service(tmp_path)

    assert definition.restart == "on-failure"
    assert definition.attempts == 3
    assert definition.restart_sec == 5.0


def test_systemd_renders_default_retry_policy(tmp_path):
    definition = service(tmp_path)

    unit = render(definition)

    assert "Restart=no" in unit
    assert "gway.service.supervisor" in unit
    assert "--restart on-failure" in unit
    assert "--attempts 3" in unit
    assert "--restart-sec 5.0" in unit


def test_systemd_renders_service_install_retry_overrides(tmp_path):
    definition = service(
        tmp_path,
        restart="always",
        attempts=7,
        restart_sec=2.0,
    )

    unit = render(definition)

    assert "Restart=no" in unit
    assert "--restart always" in unit
    assert "--attempts 7" in unit
    assert "--restart-sec 2.0" in unit


def test_service_attempts_must_be_non_negative(tmp_path):
    launchable = Launchable.operation("demo.worker", root=tmp_path)

    try:
        Service.from_launchable(
            "demo",
            "worker",
            tmp_path,
            launchable,
            attempts=-1,
        )
    except ValueError as exc:
        assert "attempts" in str(exc)
    else:
        raise AssertionError("negative attempts should fail")


def test_service_install_overrides_retry_policy(monkeypatch):
    runtime = Gateway()
    captured = {}

    class Backend:
        @staticmethod
        def install_units(project, services, **kwargs):
            captured["project"] = project
            captured["service"] = tuple(services)[0]
            captured["kwargs"] = kwargs
            return ["installed"]

    monkeypatch.setattr("gway.install.service.get", lambda name: Backend)

    result = runtime._service_controller.install(
        "sous",
        "chef",
        restart="always",
        attempts=6,
        restart_sec=1.5,
    )

    installed = captured["service"]
    assert result == ["installed"]
    assert installed.restart == "always"
    assert installed.attempts == 6
    assert installed.restart_sec == 1.5


def test_process_backend_wraps_command_with_retry_supervisor(tmp_path):
    definition = service(tmp_path)
    command = ProcessBackend._supervised_command(definition)

    assert command[:4] == [
        command[0],
        "-m",
        "gway.service.supervisor",
        "--restart",
    ]
    assert command[4:10] == [
        "on-failure",
        "--attempts",
        "3",
        "--restart-sec",
        "5.0",
        "--",
    ]
    assert command[-4:] == [
        "-m",
        "gway",
        "demo",
        "worker",
    ]


def test_process_backend_can_disable_retries(tmp_path):
    definition = service(
        tmp_path,
        restart="no",
        attempts=3,
    )
    assert ProcessBackend._supervised_command(definition) == (
        ProcessBackend._command(definition)
    )


def test_supervisor_attempts_means_retry_count(monkeypatch):
    from gway.service import supervisor

    launches = []

    class Process:
        def __init__(self, returncode):
            self.returncode = returncode

        def wait(self):
            return self.returncode

        def poll(self):
            return self.returncode

        def send_signal(self, signum):
            return None

    results = iter([1, 1, 1, 1])

    def popen(command):
        launches.append(tuple(command))
        return Process(next(results))

    monkeypatch.setattr(supervisor.subprocess, "Popen", popen)
    monkeypatch.setattr(supervisor.time, "sleep", lambda value: None)
    monkeypatch.setattr(supervisor.signal, "signal", lambda *args: None)
    monkeypatch.setattr(supervisor.signal, "getsignal", lambda signum: None)

    result = supervisor.supervise(
        ("python", "-m", "demo"),
        attempts=3,
        restart_sec=0,
    )

    assert result == 1
    assert len(launches) == 4



def test_supervisor_does_not_restart_after_stop_during_backoff(monkeypatch):
    from gway.service import supervisor

    launches = []
    handlers = {}

    class Process:
        def __init__(self, returncode):
            self.returncode = returncode

        def wait(self):
            return self.returncode

        def poll(self):
            return self.returncode

        def send_signal(self, signum):
            return None

    def popen(command):
        launches.append(tuple(command))
        return Process(1)

    def install_handler(signum, handler):
        handlers[signum] = handler

    def sleep(_seconds):
        handlers[supervisor.signal.SIGTERM](supervisor.signal.SIGTERM, None)

    monkeypatch.setattr(supervisor.subprocess, "Popen", popen)
    monkeypatch.setattr(supervisor.time, "sleep", sleep)
    monkeypatch.setattr(supervisor.signal, "signal", install_handler)
    monkeypatch.setattr(supervisor.signal, "getsignal", lambda signum: None)

    result = supervisor.supervise(
        ("python", "-m", "demo"),
        attempts=3,
        restart_sec=1,
    )

    assert result == 1
    assert len(launches) == 1
