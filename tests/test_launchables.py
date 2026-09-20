import sys

from gway.gateway import Gateway
from gway.launchable import Launchable
from gway.recipes import execute_recipe
from gway.service.model import Service
from gway.service.runtime import ProcessBackend


def test_gateway_operations_are_indexed_as_launchables():
    runtime = Gateway()

    def ping():
        return "pong"

    runtime.wrap("ping", ping)

    launchable = runtime.launchables["ping"]

    assert launchable.kind == "operation"
    assert launchable.target == "ping"
    assert launchable.command == ("{python}", "-m", "gway", "ping")


def test_recipe_execution_indexes_recipe_launchable(tmp_path):
    recipe = tmp_path / "worker.rx"
    recipe.write_text("", encoding="utf-8")
    runtime = Gateway()

    execute_recipe(runtime, recipe)

    launchable = runtime.launchables["worker"]
    assert launchable.kind == "recipe"
    assert launchable.target == recipe.resolve()
    assert launchable.command == (
        "{python}",
        "-m",
        "gway",
        str(recipe.resolve()),
    )


def test_service_can_wrap_operation_launchable(tmp_path):
    launchable = Launchable.operation("demo.worker", root=tmp_path)
    service = Service.from_launchable(
        "demo",
        "worker",
        tmp_path,
        launchable,
        restart="on-failure",
    )

    assert service.launchable is launchable
    assert service.restart == "on-failure"


def test_process_backend_executes_service_launchable_command(tmp_path):
    launchable = Launchable.operation("demo.worker", root=tmp_path)
    service = Service.from_launchable(
        "demo",
        "worker",
        tmp_path,
        launchable,
    )

    command = ProcessBackend._command(service)

    assert command == [
        sys.executable,
        "-m",
        "gway",
        "demo",
        "worker",
    ]
