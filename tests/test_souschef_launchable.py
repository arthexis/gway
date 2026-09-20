from gway.gateway import Gateway
from gway.launchable import Launchable
from gway.service.model import Service
from gway.souschef.service import definition


def test_service_requires_launchable(tmp_path):
    try:
        Service(project="demo", name="worker", root=tmp_path)
    except TypeError:
        pass
    else:
        raise AssertionError("Service should require a launchable")


def test_sous_chef_daemon_is_normal_gway_operation():
    runtime = Gateway()

    launchable = runtime.launchables["sous.chef.daemon"]
    service = runtime._services[("gway", "sous-chef")]

    assert isinstance(launchable, Launchable)
    assert launchable.kind == "operation"
    assert launchable.command == (
        "{python}",
        "-m",
        "gway",
        "sous",
        "chef",
        "daemon",
    )
    assert service.launchable is launchable


def test_sous_chef_service_definition_wraps_existing_launchable(tmp_path):
    launchable = Launchable.operation(
        "sous.chef.daemon",
        root=tmp_path,
    )

    service = definition(launchable)

    assert service.launchable is launchable
    assert service.name == "sous-chef"


def test_sous_chef_daemon_operation_runs_in_foreground(monkeypatch):
    runtime = Gateway()
    calls = []

    def foreground_run(*, poll=1.0):
        calls.append(poll)
        return "stopped"

    from gway.souschef import daemon

    wrapped = runtime.ops.resolve("sous.chef.daemon")
    wrapped.__wrapped__ = foreground_run
    monkeypatch.setattr(daemon, "run", foreground_run)

    # Re-register exactly as normal operation registration does; direct
    # invocation must synchronously return the daemon function's result.
    runtime.wrap("foreground.sous.chef", foreground_run)

    assert runtime("foreground sous chef --poll 0.25") == "stopped"
    assert calls == [0.25]
