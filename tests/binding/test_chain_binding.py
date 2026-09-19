from gway.binding import bind_arguments
from gway.tokens import Token


def test_binding_can_start_after_native_pipeline_argument(gateway):
    def filter_chargers(chargers, status: str):
        return chargers, status

    chargers = object()
    bound = bind_arguments(
        filter_chargers,
        [Token("active")],
        runtime=gateway,
        initial_args=(chargers,),
    )

    assert bound.args == (chargers, "active")


def test_binding_merges_initial_native_keywords(gateway):
    def report_chargers(chargers, *, title):
        return chargers, title

    chargers = object()
    bound = bind_arguments(
        report_chargers,
        [],
        runtime=gateway,
        initial_args=(chargers,),
        initial_kwargs={"title": "Fleet"},
    )

    assert bound.args == (chargers,)
    assert bound.kwargs == {"title": "Fleet"}


def test_numeric_sigil_outside_chain_remains_semantic_lookup(gateway):
    gateway.context["0"] = "zero"

    def echo(value):
        return value

    gateway.echo = gateway.wrap("echo_value", echo)

    assert gateway("echo [0]") == "zero"


def test_chain_negative_numeric_selector_uses_python_indexing(gateway):
    def consume(first, second):
        return first, second

    bound = bind_arguments(
        consume,
        [Token("[-1]"), Token("[0]")],
        runtime=gateway,
        pipeline=("A", "B"),
    )

    assert bound.args == ("B", "A")


def test_single_quoted_numeric_sigil_is_not_chain_selector(gateway):
    def consume(first, second):
        return first, second

    bound = bind_arguments(
        consume,
        [Token("[0]", "single")],
        runtime=gateway,
        pipeline=("A",),
    )

    assert bound.args == ("A", "[0]")
