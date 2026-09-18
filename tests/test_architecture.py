import importlib.util
from pathlib import Path

import pytest

from gway import Gateway


@pytest.mark.parametrize(
    "name",
    [
        "projects",
        "load_project",
        "find_project",
        "set_defaults",
        "clear_defaults",
        "get_default",
        "wizard",
        "wizard_enabled",
    ],
)
def test_removed_gateway_api_stays_removed(gateway, name):
    assert not hasattr(gateway, name)


def test_builtins_package_is_absent():
    assert importlib.util.find_spec("gway.builtins") is None


def test_project_declares_no_runtime_dependencies():
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    assert "dependencies = []" in text


def test_core_package_has_no_requests_import():
    root = Path(__file__).resolve().parents[1] / "gway"
    for path in root.glob("*.py"):
        assert "import requests" not in path.read_text(encoding="utf-8")


def test_same_thread_gateways_share_state():
    first = Gateway()
    first.context.clear()
    first.results.clear()
    first.context["shared"] = "yes"

    second = Gateway()
    assert second.context["shared"] == "yes"


def test_new_thread_gets_isolated_state():
    import threading

    gateway = Gateway()
    gateway.context.clear()
    gateway.context["main_only"] = True
    observed = {}

    def worker():
        other = Gateway()
        observed["has_main"] = "main_only" in other.context
        other.context["worker_only"] = True

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()

    assert observed["has_main"] is False
    assert "worker_only" not in gateway.context
