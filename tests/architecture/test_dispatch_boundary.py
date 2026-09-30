import gway.console as console
import gway.dispatch as dispatch
from gway import Gateway


def test_dispatch_module_owns_operation_resolution():
    assert callable(dispatch.resolve_operation)


def test_gateway_call_is_supported_public_execution_entrypoint():
    names = set(Gateway.__call__.__code__.co_names)
    assert "execute" in names
    assert "dispatch" not in names
    assert "process" not in names


def test_gateway_execute_is_supported_public_dispatch_entrypoint():
    names = set(Gateway.execute.__code__.co_names)
    assert "dispatch" in names
    assert "process" not in names


def test_gateway_call_and_execute_are_behaviorally_equivalent():
    via_call = Gateway()
    via_execute = Gateway()

    assert via_call("version") == via_execute.execute("version")


def test_console_process_uses_shared_dispatch_program():
    names = set(console.process.__code__.co_names)
    assert "dispatch_program" in names
    assert "dispatch_stage" not in names
    assert "bind_arguments" not in names


def test_dispatch_does_not_use_resolver_for_callable_discovery():
    names = set(dispatch.resolve_operation.__code__.co_names)
    assert "find_value" not in names
