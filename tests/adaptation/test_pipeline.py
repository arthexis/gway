import pytest

from gway.adaptation import adapt_pipeline


def test_pipeline_adapts_to_first_positional_input():
    marker = object()

    def consume(value):
        return value

    adapted = adapt_pipeline(None, consume, marker)

    assert adapted.args == (marker,)
    assert adapted.kwargs == {}


def test_pipeline_precedes_explicit_native_arguments():
    marker = object()

    def filter_items(items, status):
        return items, status

    adapted = adapt_pipeline(None, filter_items, marker, args=("active",))

    assert adapted.args == ("active", marker)


def test_pipeline_preserves_native_keyword_arguments():
    marker = object()

    def report(items, *, title):
        return items, title

    adapted = adapt_pipeline(
        None,
        report,
        marker,
        kwargs={"title": "Fleet"},
    )

    assert adapted.args == (marker,)
    assert adapted.kwargs == {"title": "Fleet"}


def test_consumer_semantic_subject_is_preferred(gateway):
    marker = object()

    def summarize(prefix, chargers):
        return prefix, chargers

    wrapped = gateway.wrap("summarize_chargers", summarize)
    adapted = adapt_pipeline(gateway, wrapped, marker)

    assert adapted.args == ()
    assert adapted.kwargs == {"chargers": marker}


def test_producer_subject_name_is_used_when_consumer_subject_does_not_match(gateway):
    marker = object()
    gateway.results.insert("chargers", marker)

    def summarize(prefix, chargers):
        return prefix, chargers

    adapted = adapt_pipeline(gateway, summarize, marker)

    assert adapted.args == ()
    assert adapted.kwargs == {"chargers": marker}


def test_compatible_annotation_precedes_positional_fallback():
    marker = ["A"]

    def summarize(prefix: str, items: list):
        return prefix, items

    adapted = adapt_pipeline(None, summarize, marker)

    assert adapted.args == ()
    assert adapted.kwargs == {"items": marker}


def test_union_annotation_can_match_pipeline_value():
    marker = ["A"]

    def summarize(prefix: str, items: list | tuple):
        return prefix, items

    adapted = adapt_pipeline(None, summarize, marker)

    assert adapted.kwargs == {"items": marker}


def test_explicit_keyword_is_not_overwritten_by_adaptation(gateway):
    marker = object()
    explicit = object()

    def summarize(chargers, fallback):
        return chargers, fallback

    wrapped = gateway.wrap("summarize_chargers", summarize)
    adapted = adapt_pipeline(
        gateway,
        wrapped,
        marker,
        kwargs={"chargers": explicit},
    )

    assert adapted.args == ()
    assert adapted.kwargs == {"chargers": explicit, "fallback": marker}


def test_pipeline_rejects_consumer_without_available_parameter():
    def report(*, title):
        return title

    with pytest.raises(TypeError, match="no available parameter"):
        adapt_pipeline(None, report, object(), kwargs={"title": "Fleet"})
