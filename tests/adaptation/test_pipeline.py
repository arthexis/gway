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
    assert plan.parameter == "items"
    assert adapted.args == (marker, "active")


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


def test_pipeline_uses_first_available_positional_regardless_of_subject_name(gateway):
    marker = object()
    gateway.results.insert("chargers", marker)

    def summarize(prefix, chargers):
        return prefix, chargers

    wrapped = gateway.wrap("summarize_chargers", summarize)
    plan = plan_pipeline(gateway, wrapped, marker)
    adapted = apply_plan(wrapped, plan, marker)

    assert plan.rule == "positional"
    assert plan.parameter == "prefix"
    assert plan.producer_subject == "chargers"
    assert adapted.args == (marker,)


def test_pipeline_does_not_route_by_annotation():
    marker = ["A"]

    def summarize(prefix: str, items: list):
        return prefix, items

    plan = plan_pipeline(None, summarize, marker)
    adapted = apply_plan(summarize, plan, marker)

    assert plan.rule == "positional"
    assert plan.parameter == "prefix"
    assert adapted.args == (marker,)


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

    with pytest.raises(TypeError, match="no available positional parameter"):
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


def test_pipeline_positional_value_precedes_named_context(gateway):
    raw = ["pipeline"]
    gateway.context["chargers"] = ["context"]

    def consume(chargers):
        return chargers

    wrapped = gateway.wrap("consume_report", consume)
    adapted = adapt_pipeline(gateway, wrapped, raw)

    assert adapted.args == (raw,)
    assert wrapped(*adapted.args, **adapted.kwargs) is raw


def test_tuple_pipeline_expands_into_positional_prefix():
    def consume(first, second, third):
        return first, second, third

    adapted = adapt_pipeline(
        None,
        consume,
        ("A", "B"),
        args=("C",),
    )

    assert adapted.args == ("A", "B", "C")
    assert adapted.kwargs == {}


def test_list_pipeline_remains_one_positional_value():
    value = ["A", "B"]

    def consume(items, status):
        return items, status

    adapted = adapt_pipeline(
        None,
        consume,
        value,
        args=("active",),
    )

    assert adapted.args == (value, "active")
