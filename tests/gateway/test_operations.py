from gway import Operations


def test_ops_is_mapping_like_registry(gateway):
    assert isinstance(gateway.ops, Operations)

    def chargers():
        return ["A"]

    wrapped = gateway.wrap("get_chargers", chargers)
    gateway.chargers = wrapped

    assert "get_chargers" in gateway.ops
    assert "chargers" in gateway.ops
    assert gateway.ops["get_chargers"] is wrapped
    assert gateway.ops["chargers"] is wrapped
    assert set(gateway.ops) >= {"get_chargers", "chargers"}
    assert len(gateway.ops) >= 2


def test_dispatch_resolves_registered_operation_without_gateway_attribute(gateway):
    def ping():
        return "pong"

    wrapped = gateway.wrap("ping", ping)

    assert "ping" in gateway.ops
    assert "ping" not in gateway.__dict__
    assert gateway("ping") == "pong"
    assert gateway.ops["ping"] is wrapped


def test_ops_can_register_and_unregister_callable():
    ops = Operations()

    def ping():
        return "pong"

    assert ops.register("ping", ping) is ping
    assert "ping" in ops
    assert ops["ping"]() == "pong"
    assert ops.unregister("ping") is ping
    assert "ping" not in ops
