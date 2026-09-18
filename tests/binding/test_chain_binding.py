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
