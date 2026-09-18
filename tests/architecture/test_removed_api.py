import importlib.util

import pytest


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
