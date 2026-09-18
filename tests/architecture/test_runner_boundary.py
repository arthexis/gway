import importlib.util

import gway.runner as runner
from gway import Gateway


def test_runner_module_owns_invocation_contract():
    assert callable(runner.invoke)


def test_invocation_compatibility_module_is_removed():
    assert importlib.util.find_spec("gway.invocation") is None


def test_gateway_no_longer_inherits_legacy_runner_class():
    assert "Runner" not in {base.__name__ for base in Gateway.__mro__}
