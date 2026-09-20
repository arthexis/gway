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


def test_negative_boolean_flag_sets_known_parameter_false(gateway):
    def operation(*, enabled: bool = True):
        return enabled

    bound = bind_arguments(
        operation,
        [Token("--no-enabled")],
        runtime=gateway,
    )

    assert bound.args == ()
    assert bound.kwargs == {"enabled": False}


def test_plural_sequence_option_accepts_comma_separated_values(gateway):
    def operation(*, services: tuple[str, ...] = ()):
        return services

    bound = bind_arguments(
        operation,
        [Token("--services"), Token("web,worker")],
        runtime=gateway,
    )

    assert bound.kwargs == {"services": ("web", "worker")}


def test_singular_sequence_option_is_inferred(gateway):
    def operation(*, services: tuple[str, ...] = ()):
        return services

    bound = bind_arguments(
        operation,
        [Token("--service"), Token("worker")],
        runtime=gateway,
    )

    assert bound.kwargs == {"services": ("worker",)}


def test_singular_sequence_option_rejects_multiple_items(gateway):
    def operation(*, services: tuple[str, ...] = ()):
        return services

    with pytest.raises(TypeError, match="exactly one item"):
        bind_arguments(
            operation,
            [Token("--service"), Token("web,worker")],
            runtime=gateway,
        )


def test_singular_sequence_option_handles_irregular_alias_plural(gateway):
    def operation(*, aliases: list[str] = []):
        return aliases

    bound = bind_arguments(
        operation,
        [Token("--alias"), Token("short")],
        runtime=gateway,
    )

    assert bound.kwargs == {"aliases": ["short"]}


def test_plural_inference_requires_sequence_annotation(gateway):
    def operation(*, services: str = ""):
        return services

    with pytest.raises(TypeError, match="Unknown argument"):
        bind_arguments(
            operation,
            [Token("--service"), Token("worker")],
            runtime=gateway,
        )
