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
