import gway.invocation as invocation
import gway.runner as runner
from gway import Gateway


def test_runner_module_owns_invocation_contract():
    assert callable(runner.invoke)


def test_invocation_module_is_compatibility_alias():
    assert invocation.invoke is runner.invoke


def test_gateway_no_longer_inherits_legacy_runner_class():
    assert "Runner" not in {base.__name__ for base in Gateway.__mro__}
