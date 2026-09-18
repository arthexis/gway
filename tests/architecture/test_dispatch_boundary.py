import gway.console as console
import gway.dispatch as dispatch
from gway import Gateway


def test_dispatch_module_owns_operation_resolution():
    assert callable(dispatch.resolve_operation)
    assert not hasattr(console, "_resolve_operation")


def test_gateway_call_delegates_to_dispatch_module():
    names = set(Gateway.__call__.__code__.co_names)
    assert "dispatch" in names
    assert "process" not in names


def test_console_process_uses_dispatch_stage():
    names = set(console.process.__code__.co_names)
    assert "dispatch_stage" in names
    assert "bind_arguments" not in names
