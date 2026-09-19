import gway.console as console
import gway.dispatch as dispatch
from gway import Gateway


def test_dispatch_module_owns_operation_resolution():
    assert callable(dispatch.resolve_operation)


def test_gateway_call_delegates_to_dispatch_module():
    names = set(Gateway.__call__.__code__.co_names)
    assert "dispatch" in names
    assert "process" not in names


def test_console_process_uses_shared_dispatch_sequence():
    names = set(console.process.__code__.co_names)
    assert "dispatch_sequence" in names
    assert "dispatch_stage" not in names
    assert "bind_arguments" not in names


def test_dispatch_does_not_use_resolver_for_callable_discovery():
    names = set(dispatch.resolve_operation.__code__.co_names)
    assert "find_value" not in names
