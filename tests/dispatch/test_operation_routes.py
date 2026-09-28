import pytest

from gway import Gateway
from gway.routes import OperationRoute, OperationRoutes


def test_operation_route_requires_name_and_callable():
    with pytest.raises(ValueError, match="non-empty name"):
        OperationRoute("", lambda runtime, tokens: False)

    with pytest.raises(TypeError, match="must be callable"):
        OperationRoute("broken", None)


def test_operation_routes_preserve_registration_order():
    routes = OperationRoutes()
    calls = []

    routes.register("first", lambda runtime, tokens: calls.append("first") or False)
    routes.register("second", lambda runtime, tokens: calls.append("second") or True)
    routes.register("third", lambda runtime, tokens: calls.append("third") or True)

    assert routes.expand(object(), ["inspect"]) is True
    assert calls == ["first", "second"]


def test_operation_routes_reject_duplicate_names():
    routes = OperationRoutes()
    routes.register("custom", lambda runtime, tokens: False)

    with pytest.raises(ValueError, match="already registered"):
        routes.register("custom", lambda runtime, tokens: False)


def test_gateway_registers_sampler_as_default_fallback_route():
    gateway = Gateway()

    assert tuple(route.name for route in gateway.operation_routes.routes) == ("sampler",)


def test_dispatch_uses_generic_operation_route_before_lookup_failure():
    gateway = Gateway()

    def expand(runtime, tokens):
        def inspect_fixture(value=None):
            return f"route:{value}"

        runtime.wrap(
            "inspect.fixture",
            inspect_fixture,
            op="inspect",
            sub="fixture",
        )
        return True

    gateway.operation_routes = OperationRoutes()
    gateway.operation_routes.register("fixture", expand)

    assert gateway("inspect fixture alpha") == "route:alpha"
