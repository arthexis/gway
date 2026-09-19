import pytest

from gway.binding import bind_arguments
from gway.tokens import Token


def test_unknown_keyword_fails_cleanly(gateway):
    def operation(value: str):
        return value

    with pytest.raises(TypeError, match="Unknown argument"):
        bind_arguments(
            operation,
            [Token("--missing"), Token("x")],
            runtime=gateway,
        )


def test_double_dash_ends_option_parsing(gateway):
    def operation(value: str):
        return value

    bound = bind_arguments(
        operation,
        [Token("--"), Token("--special")],
        runtime=gateway,
    )
    assert bound.args == ("--special",)


def test_missing_required_arguments_are_left_for_semantic_binding(gateway):
    def inspect_charger(charger):
        return charger

    bound = bind_arguments(inspect_charger, [], runtime=gateway)
    assert bound.args == ()
    assert bound.kwargs == {}


def test_variadic_positional_arguments_receive_sigil_resolution(gateway):
    gateway.context["path"] = "/tmp/example"

    def operation(*parts):
        return parts

    bound = bind_arguments(
        operation,
        [Token("[path]")],
        runtime=gateway,
    )

    assert bound.args == ("/tmp/example",)
