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


def _write_route_package(root, relative, body):
    package = root.joinpath(*relative.split("/"))
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text(body, encoding="utf-8")
    return package


def test_route_can_be_inserted_before_sampler():
    gateway = Gateway()
    gateway.operation_routes.register(
        "explicit",
        lambda runtime, tokens: False,
        before="sampler",
    )

    assert tuple(route.name for route in gateway.operation_routes.routes) == (
        "explicit",
        "sampler",
    )


def test_add_operation_root_normalizes_and_prioritizes_before_sampler(tmp_path):
    gateway = Gateway()
    relative = tmp_path / "ops"
    relative.mkdir()

    resolved = gateway.add_operation_root(relative)

    assert resolved == relative.resolve()
    assert tuple(route.name for route in gateway.operation_routes.routes) == (
        f"root:{relative.resolve()}",
        "sampler",
    )


def test_add_operation_root_rejects_missing_directory(tmp_path):
    gateway = Gateway()

    with pytest.raises(ValueError, match="not a directory"):
        gateway.add_operation_root(tmp_path / "missing")


def test_cli_root_discovers_sampler_style_capability(run_cli, tmp_path):
    root = tmp_path / "ops"
    _write_route_package(
        root,
        "feature/widget",
        """
def register(runtime):
    def inspect_widget(value=None):
        return f"explicit:{value}"
    runtime.wrap("inspect.widget", inspect_widget, op="inspect", sub="widget")
""",
    )

    status, stdout, stderr = run_cli(
        "-R",
        str(root),
        "inspect",
        "widget",
        "alpha",
    )

    assert status == 0
    assert stdout.strip() == "explicit:alpha"
    assert stderr == ""


def test_cli_roots_use_left_to_right_precedence(run_cli, tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    for root, result in ((first, "first"), (second, "second")):
        _write_route_package(
            root,
            "feature/widget",
            f"""
def register(runtime):
    def inspect_widget(value=None):
        return "{result}"
    runtime.wrap("inspect.widget", inspect_widget, op="inspect", sub="widget")
""",
        )

    status, stdout, stderr = run_cli(
        "-R",
        str(first),
        "-R",
        str(second),
        "inspect",
        "widget",
    )

    assert status == 0
    assert stdout.strip() == "first"
    assert stderr == ""


def test_cli_root_is_not_persistent_across_invocations(run_cli, tmp_path):
    root = tmp_path / "ops"
    _write_route_package(
        root,
        "feature/widget",
        """
def register(runtime):
    runtime.wrap(
        "inspect.widget",
        lambda: "temporary",
        op="inspect",
        sub="widget",
    )
""",
    )

    first = run_cli("-R", str(root), "inspect", "widget")
    second = run_cli("inspect", "widget")

    assert first[0] == 0
    assert first[1].strip() == "temporary"
    assert second[0] == 2
    assert "Unable to resolve operation" in second[2]


def test_operation_root_is_not_a_remote_operation(tmp_path):
    gateway = Gateway()
    root = tmp_path / "ops"
    root.mkdir()
    gateway.add_operation_root(root)

    assert gateway.ops.resolve("root") is None
    assert gateway.ops.resolve("add.root") is None
