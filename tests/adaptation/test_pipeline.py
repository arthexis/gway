import pytest

from gway.adaptation import adapt_pipeline


def test_pipeline_adapts_to_first_positional_input():
    marker = object()

    def consume(value):
        return value

    adapted = adapt_pipeline(consume, marker)

    assert adapted.args == (marker,)
    assert adapted.kwargs == {}


def test_pipeline_precedes_explicit_native_arguments():
    marker = object()

    def filter_items(items, status):
        return items, status

    adapted = adapt_pipeline(filter_items, marker, args=("active",))

    assert adapted.args == (marker, "active")


def test_pipeline_preserves_native_keyword_arguments():
    marker = object()

    def report(items, *, title):
        return items, title

    adapted = adapt_pipeline(report, marker, kwargs={"title": "Fleet"})

    assert adapted.args == (marker,)
    assert adapted.kwargs == {"title": "Fleet"}


def test_pipeline_rejects_consumer_without_positional_capacity():
    def report(*, title):
        return title

    with pytest.raises(TypeError):
        adapt_pipeline(report, object(), kwargs={"title": "Fleet"})
