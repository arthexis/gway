from pathlib import Path

from gway.gateway import Gateway


def test_service_inspect_accepts_any_operation():
    runtime = Gateway()

    def worker(poll=1.0):
        return poll

    runtime.wrap("worker", worker)

    details = runtime("service inspect worker")

    assert details["project"] == "gway"
    assert details["service"] == "worker"
    assert details["launchable"]["kind"] == "operation"
    assert details["launchable"]["command"] == [
        "{python}",
        "-m",
        "gway",
        "worker",
    ]


def test_service_install_preserves_target_arguments_after_separator(monkeypatch):
    runtime = Gateway()
    captured = {}

    def worker(*, poll=1.0):
        return poll

    runtime.wrap("worker", worker)

    class Backend:
        @staticmethod
        def install_units(project, services, **kwargs):
            captured["project"] = project
            captured["service"] = tuple(services)[0]
            captured["kwargs"] = kwargs
            return ["installed"]

    monkeypatch.setattr("gway.install.backends.get", lambda name: Backend)

    result = runtime(
        "service install --backend process --attempts 5 "
        "-- worker --poll 2"
    )

    definition = captured["service"]
    assert result == ["installed"]
    assert definition.attempts == 5
    assert definition.launchable.command == (
        "{python}",
        "-m",
        "gway",
        "worker",
        "--poll",
        "2",
    )


def test_service_install_accepts_recipe_path(tmp_path, monkeypatch):
    runtime = Gateway()
    recipe = tmp_path / "worker.rx"
    recipe.write_text("", encoding="utf-8")
    captured = {}

    class Backend:
        @staticmethod
        def install_units(project, services, **kwargs):
            captured["service"] = tuple(services)[0]
            return ["installed"]

    monkeypatch.setattr("gway.install.backends.get", lambda name: Backend)

    result = runtime(
        f"service install --backend process -- {recipe}"
    )

    definition = captured["service"]
    assert result == ["installed"]
    assert definition.launchable.kind == "recipe"
    assert definition.launchable.target == recipe.resolve()
    assert definition.launchable.command == (
        "{python}",
        "-m",
        "gway",
        str(recipe.resolve()),
    )


def test_service_start_accepts_any_operation_without_preset():
    runtime = Gateway()
    calls = []

    def worker():
        return None

    runtime.wrap("worker", worker)

    class Backend:
        def start(self, definition):
            calls.append(definition)
            return {"running": True, "service": definition.name}

    runtime._service_controller.backend = Backend()

    result = runtime("service start worker")

    assert result == {"running": True, "service": "worker"}
    assert calls[0].launchable.name == "worker"


def test_named_service_identity_allows_multiple_invocations(monkeypatch):
    runtime = Gateway()
    captured = []

    def worker(*, queue="default"):
        return queue

    runtime.wrap("worker", worker)

    class Backend:
        @staticmethod
        def install_units(project, services, **kwargs):
            captured.append(tuple(services)[0])
            return ["installed"]

    monkeypatch.setattr("gway.install.backends.get", lambda name: Backend)

    runtime(
        "service install --backend process --name urgent "
        "-- worker --queue urgent"
    )
    runtime(
        "service install --backend process --name bulk "
        "-- worker --queue bulk"
    )

    assert [item.name for item in captured] == ["urgent", "bulk"]
    assert captured[0].launchable.command[-2:] == ("--queue", "urgent")
    assert captured[1].launchable.command[-2:] == ("--queue", "bulk")


def test_installed_service_record_preserves_launchable_invocation(tmp_path):
    from gway.install.systemd import UnitRecord, UnitState

    state = UnitState(tmp_path / "state")
    state.put(
        "demo",
        [
            UnitRecord(
                project="demo",
                service="urgent",
                unit="demo-urgent.service",
                backend="process",
                restart="on-failure",
                attempts=3,
                restart_sec=5.0,
                command=(
                    "{python}",
                    "-m",
                    "gway",
                    "worker",
                    "--queue",
                    "urgent",
                ),
            )
        ],
    )

    restored = state.get("demo")[0]

    assert restored.command[-2:] == ("--queue", "urgent")
    assert restored.attempts == 3
