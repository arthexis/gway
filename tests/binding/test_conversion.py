from gway.binding import Literal, bind_arguments
from gway.tokens import Token


def test_integer_conversion_happens_at_binding_boundary(gateway):
    def operation(limit: int):
        return limit

    bound = bind_arguments(operation, [Token("32")], runtime=gateway)
    assert bound.args == (32,)


def test_boolean_conversion_happens_at_binding_boundary(gateway):
    def operation(enabled: bool):
        return enabled

    assert bind_arguments(operation, [Token("yes")], runtime=gateway).args == (True,)
    assert bind_arguments(operation, [Token("off")], runtime=gateway).args == (False,)


def test_single_quoted_literal_bypasses_conversion(gateway):
    def operation(limit: int):
        return limit

    bound = bind_arguments(operation, [Token("32", "single")], runtime=gateway)
    assert isinstance(bound.args[0], Literal)
    assert bound.args[0] == "32"


def test_sigil_conversion_uses_runtime_before_annotation(gateway):
    gateway.context["limit"] = "32"

    def operation(limit: int):
        return limit

    bound = bind_arguments(operation, [Token("[limit]")], runtime=gateway)
    assert bound.args == (32,)
