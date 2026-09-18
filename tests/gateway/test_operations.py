from gway import Operations, Subjects


def test_ops_and_subs_are_shared_semantic_views(gateway):
    def get_chargers():
        return ["A"]

    def start_chargers(chargers):
        return chargers

    get_wrapped = gateway.wrap("get_chargers", get_chargers)
    start_wrapped = gateway.wrap("start_chargers", start_chargers)
    gateway.chargers = get_wrapped

    assert isinstance(gateway.ops, Operations)
    assert isinstance(gateway.subs, Subjects)

    assert set(gateway.ops) >= {"get", "start"}
    assert "chargers" in gateway.subs

    assert gateway.ops["get"]["chargers"] is get_wrapped
    assert gateway.ops["start"]["chargers"] is start_wrapped
    assert gateway.subs["chargers"]["get"] is get_wrapped
    assert gateway.subs["chargers"]["start"] is start_wrapped


def test_public_aliases_do_not_pollute_ops_or_subs(gateway):
    def get_chargers():
        return ["A"]

    wrapped = gateway.wrap("get_chargers", get_chargers)
    gateway.chargers = wrapped

    assert "chargers" not in gateway.ops
    assert set(gateway.ops) == {"get"}
    assert set(gateway.subs) == {"chargers"}
    assert gateway.ops.resolve("chargers") is wrapped


def test_dispatch_resolves_registered_operation_without_gateway_attribute(gateway):
    def ping():
        return "pong"

    wrapped = gateway.wrap("ping", ping)

    assert "ping" in gateway.ops
    assert "ping" not in gateway.__dict__
    assert gateway("ping") == "pong"
    assert gateway.ops["ping"][None] is wrapped


def test_ops_can_register_and_unregister_callable():
    ops = Operations()

    def inspect_charger():
        return "ok"

    assert ops.register("inspect_charger", inspect_charger) is inspect_charger
    assert "inspect" in ops
    assert ops["inspect"]["charger"] is inspect_charger
    assert ops.resolve("inspect_charger") is inspect_charger
    assert ops.unregister("inspect_charger") is inspect_charger
    assert "inspect" not in ops


def test_unsubjected_operation_does_not_create_subject():
    ops = Operations()

    def ping():
        return "pong"

    ops.register("ping", ping)

    assert "ping" in ops
    assert ops["ping"][None] is ping
