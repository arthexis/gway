import pytest

from gway.adaptation import AdaptationPlan, adapt_pipeline, apply_plan, plan_pipeline


def test_pipeline_adapts_to_first_positional_input():
    marker = object()

    def consume(value):
        return value

    plan = plan_pipeline(None, consume, marker)
    adapted = adapt_pipeline(None, consume, marker)

    assert plan == AdaptationPlan("positional", "value", None, None)
    assert adapted.args == (marker,)
    assert adapted.kwargs == {}


def test_pipeline_precedes_explicit_native_arguments():
    marker = object()

    def filter_items(items, status):
        return items, status

    plan = plan_pipeline(None, filter_items, marker, args=("active",))
    adapted = apply_plan(filter_items, plan, marker, args=("active",))

    assert plan.rule == "positional"
    assert plan.parameter == "status"
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
    plan = plan_pipeline(gateway, wrapped, marker)
    adapted = apply_plan(wrapped, plan, marker)

    assert plan.rule == "consumer_subject"
    assert plan.parameter == "chargers"
    assert plan.consumer_subject == "chargers"
    assert adapted.kwargs == {"chargers": marker}


def test_producer_subject_name_is_used_when_consumer_subject_does_not_match(gateway):
    marker = object()
    gateway.results.insert("chargers", marker)

    def summarize(prefix, chargers):
        return prefix, chargers

    plan = plan_pipeline(gateway, summarize, marker)

    assert plan.rule == "producer_subject"
    assert plan.parameter == "chargers"
    assert plan.producer_subject == "chargers"


def test_compatible_annotation_precedes_positional_fallback():
    marker = ["A"]

    def summarize(prefix: str, items: list):
        return prefix, items

    plan = plan_pipeline(None, summarize, marker)
    adapted = apply_plan(summarize, plan, marker)

    assert plan.rule == "annotation"
    assert plan.parameter == "items"
    assert adapted.kwargs == {"items": marker}


def test_union_annotation_can_match_pipeline_value():
    marker = ["A"]

    def summarize(prefix: str, items: list | tuple):
        return prefix, items

    plan = plan_pipeline(None, summarize, marker)

    assert plan.rule == "annotation"
    assert plan.parameter == "items"


def test_explicit_keyword_is_not_overwritten_by_adaptation(gateway):
    marker = object()
    explicit = object()

    def summarize(chargers, fallback):
        return chargers, fallback

    wrapped = gateway.wrap("summarize_chargers", summarize)
    plan = plan_pipeline(
        gateway,
        wrapped,
        marker,
        kwargs={"chargers": explicit},
    )
    adapted = apply_plan(
        wrapped,
        plan,
        marker,
        kwargs={"chargers": explicit},
    )

    assert plan.parameter == "fallback"
    assert adapted.kwargs == {"chargers": explicit, "fallback": marker}


def test_pipeline_rejects_consumer_without_available_parameter():
    def report(*, title):
        return title

    with pytest.raises(TypeError, match="no available parameter"):
        plan_pipeline(None, report, object(), kwargs={"title": "Fleet"})


def test_pipeline_can_satisfy_semantic_method_receiver(gateway):
    class Device:
        def label(self, prefix):
            return f"{prefix}:device"

    device = Device()
    gateway.results.insert("device", device)
    wrapped = gateway.wrap(
        "device.label",
        Device.label,
        receiver="device",
    )

    plan = plan_pipeline(gateway, wrapped, device)
    adapted = apply_plan(wrapped, plan, device)

    assert plan == AdaptationPlan("receiver", None, "device", "device")
    assert adapted.args == ()
    assert adapted.kwargs == {}
