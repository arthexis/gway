import pytest


def test_gateway_executes_command_line_string(gateway):
    def echo(value: str):
        return value

    gateway.echo = gateway.wrap("echo_value", echo)
    assert gateway("echo hello") == "hello"


def test_gateway_executes_multiple_command_stages(gateway):
    def get_charger():
        return "CHG001"

    def inspect_charger(charger):
        return f"inspect:{charger}"

    gateway.get_charger = gateway.wrap("get_charger", get_charger)
    gateway.inspect_charger = gateway.wrap("inspect_charger", inspect_charger)

    assert gateway("get_charger - inspect_charger") == "inspect:CHG001"


def test_gateway_accepts_native_positional_arguments(gateway):
    value = object()

    def echo(item):
        return item

    gateway.echo = gateway.wrap("echo_item", echo)
    assert gateway("echo", value) is value


def test_gateway_accepts_native_keyword_arguments(gateway):
    marker = object()

    def configure(*, value):
        return value

    gateway.configure = gateway.wrap("configure_value", configure)
    assert gateway("configure", value=marker) is marker


def test_gateway_native_arguments_bypass_command_line_coercion(gateway):
    def set_limit(limit: int):
        return limit

    gateway.set_limit = gateway.wrap("set_limit", set_limit)
    assert gateway("set_limit", "32") == "32"


def test_gateway_rejects_inline_and_native_arguments_together(gateway):
    def echo(value):
        return value

    gateway.echo = gateway.wrap("echo_value", echo)

    with pytest.raises(TypeError, match="without inline arguments"):
        gateway("echo inline", "native")



def test_non_mutating_execution_forces_mutate_false(gateway):
    seen = []

    def inspect_state(*, mutate=True):
        seen.append(mutate)
        return mutate

    gateway.inspect_state = gateway.wrap("inspect_state", inspect_state)

    assert gateway.execute("inspect_state", mutate=False) is False
    assert seen == [False]


def test_non_mutating_execution_rejects_undeclared_callable_before_invocation(gateway):
    called = []

    def restart():
        called.append(True)
        return "restarted"

    gateway.restart = gateway.wrap("restart_service", restart)

    with pytest.raises(
        RuntimeError,
        match="does not support non-mutating execution",
    ):
        gateway.execute("restart service", mutate=False)

    assert called == []


def test_normal_execution_preserves_callable_mutation_default(gateway):
    def inspect_default(*, mutate=False):
        return mutate

    def refresh_default(*, mutate=True):
        return mutate

    gateway.inspect_default = gateway.wrap("inspect_default", inspect_default)
    gateway.refresh_default = gateway.wrap("refresh_default", refresh_default)

    assert gateway("inspect_default") is False
    assert gateway("refresh_default") is True


def test_nested_execution_cannot_reenable_mutation(gateway):
    seen = []

    def child(*, mutate=True):
        seen.append(("child", mutate))
        return mutate

    def parent(*, mutate=True):
        seen.append(("parent", mutate))
        return gateway.execute("child", mutate=True)

    gateway.child = gateway.wrap("child", child)
    gateway.parent = gateway.wrap("parent", parent)

    assert gateway.execute("parent", mutate=False) is False
    assert seen == [("parent", False), ("child", False)]
    assert gateway.mutation_allowed is True


def test_nested_plain_gateway_call_inherits_non_mutating_execution(gateway):
    def child(*, mutate=True):
        return mutate

    def parent(*, mutate=True):
        return gateway("child")

    gateway.child = gateway.wrap("child", child)
    gateway.parent = gateway.wrap("parent", parent)

    assert gateway.execute("parent", mutate=False) is False



def test_non_mutating_execution_restores_gway_runtime_bookkeeping(gateway):
    gateway.context["seed"] = "before"
    gateway.results.insert("seed", "before")
    initial_context = dict(gateway.context)
    initial_results = dict(gateway.results.get_results())
    initial_history = list(gateway.results.history)
    previous_execution = gateway.execution
    previous_previous_execution = gateway.previous_execution

    def inspect(*, mutate=False):
        return {"observed": "value", "mutate": mutate}

    gateway.inspect = gateway.wrap("inspect_state", inspect)

    result = gateway.execute("inspect", mutate=False)

    assert result == {"observed": "value", "mutate": False}
    assert gateway.context == initial_context
    assert gateway.results.get_results() == initial_results
    assert gateway.results.history == initial_history
    assert gateway.execution is previous_execution
    assert gateway.previous_execution is previous_previous_execution


def test_repeated_non_mutating_execution_does_not_grow_result_history(gateway):
    def inspect(*, mutate=False):
        return "ok"

    gateway.inspect = gateway.wrap("inspect_state", inspect)
    initial_history = list(gateway.results.history)

    for _ in range(25):
        assert gateway.execute("inspect", mutate=False) == "ok"

    assert gateway.results.history == initial_history


def test_failed_non_mutating_execution_restores_gway_runtime_bookkeeping(gateway):
    gateway.context["seed"] = "before"
    gateway.results.insert("seed", "before")
    initial_context = dict(gateway.context)
    initial_results = dict(gateway.results.get_results())
    initial_history = list(gateway.results.history)

    def inspect(*, mutate=False):
        gateway.context["temporary"] = True
        raise ValueError("boom")

    gateway.inspect = gateway.wrap("inspect_state", inspect)

    with pytest.raises(ValueError, match="boom"):
        gateway.execute("inspect", mutate=False)

    assert gateway.context == initial_context
    assert gateway.results.get_results() == initial_results
    assert gateway.results.history == initial_history
