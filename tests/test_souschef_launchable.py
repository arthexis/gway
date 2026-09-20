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


def test_sous_chef_entrypoint_is_normal_gway_operation():
    runtime = Gateway()

    launchable = runtime.launchables["sous.chef"]
    service = runtime._services[("gway", "sous-chef")]

    assert isinstance(launchable, Launchable)
    assert launchable.kind == "operation"
    assert launchable.command == (
        "{python}",
        "-m",
        "gway",
        "sous",
        "chef",
    )
    assert service.launchable is launchable


def test_sous_chef_service_definition_wraps_existing_launchable(tmp_path):
    launchable = Launchable.operation(
        "sous.chef",
        root=tmp_path,
    )

    service = definition(launchable)

    assert service.launchable is launchable
    assert service.name == "sous-chef"


def test_sous_chef_entrypoint_operation_runs_in_foreground(monkeypatch):
    runtime = Gateway()
    events = []

    class StopAfterOneWait:
        def __init__(self):
            self.stopped = False

        def is_set(self):
            return self.stopped

        def set(self):
            self.stopped = True

        def wait(self, poll):
            events.append(("wait", poll))
            self.stopped = True

    class Scheduler:
        def drain(self):
            events.append(("drain", None))

    class Engine:
        def __init__(self, *args, **kwargs):
            self.scheduler = Scheduler()

        def evaluate(self):
            events.append(("evaluate", None))

    import gway.souschef as souschef

    monkeypatch.setattr(souschef.threading, "Event", StopAfterOneWait)
    monkeypatch.setattr(entrypoint, "TriggerEngine", Engine)
    monkeypatch.setattr(souschef.signal, "signal", lambda *args: None)

    result = runtime("sous chef --poll 0.25")

    assert result == 0
    assert events == [
        ("evaluate", None),
        ("drain", None),
        ("wait", 0.25),
    ]
