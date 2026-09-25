from gway import Gateway


def test_bare_gateway_does_not_eagerly_register_app_operations():
    gateway = Gateway()

    assert gateway.ops.resolve("setup.app") is None
    assert gateway.ops.resolve("serve.app") is None
    assert gateway.ops.resolve("expose.app") is None


def test_sampler_fallback_loads_app_only_after_resolution_miss():
    gateway = Gateway()

    app = gateway("setup app remote")

    assert app.name == "remote"
    assert gateway.ops.resolve("setup.app") is not None
    assert gateway.ops.resolve("view.app") is not None
    assert gateway.ops.resolve("expose.app") is not None


def test_existing_operation_wins_before_sampler_fallback():
    gateway = Gateway()
    calls = []

    def setup_app(name=None):
        calls.append(name)
        return "builtin-wins"

    gateway.wrap("setup.app", setup_app, op="setup", sub="app")

    assert gateway("setup app remote") == "builtin-wins"
    assert calls == ["remote"]
    assert getattr(gateway, "_sampler_routes", set()) == set()


def test_sampler_fallback_is_not_reloaded_after_first_use():
    gateway = Gateway()

    first = gateway("setup app remote")
    loaded = set(gateway._sampler_routes)
    second = gateway("setup app second")

    assert first.name == "remote"
    assert second.name == "second"
    assert gateway._sampler_routes == loaded


def _write_sampler_package(root, relative, body):
    package = root.joinpath(*relative.split("/"))
    package.mkdir(parents=True, exist_ok=True)
    (package / "__init__.py").write_text(body, encoding="utf-8")
    return package


def test_sampler_fallback_is_generic_and_not_app_specific(tmp_path, monkeypatch):
    import gway.sampler as sampler

    _write_sampler_package(
        tmp_path,
        "widgets/tool",
        """
def register(runtime):
    def inspect_widget(name=None):
        return f"widget:{name}"
    runtime.wrap("inspect.widget", inspect_widget, op="inspect", sub="widget")
""",
    )
    monkeypatch.setattr(sampler, "root", lambda: tmp_path)

    gateway = Gateway()

    assert gateway("inspect widget alpha") == "widget:alpha"


def test_sampler_fallback_loads_one_route_then_restarts_normal_resolution(
    tmp_path,
    monkeypatch,
):
    import gway.sampler as sampler

    first = _write_sampler_package(
        tmp_path,
        "alpha/other",
        """
def register(runtime):
    runtime._first_sampler_probe = True
""",
    )
    second = _write_sampler_package(
        tmp_path,
        "beta/widget",
        """
def register(runtime):
    def inspect_widget(name=None):
        return f"resolved:{name}"
    runtime.wrap("inspect.widget", inspect_widget, op="inspect", sub="widget")
""",
    )
    monkeypatch.setattr(sampler, "root", lambda: tmp_path)

    gateway = Gateway()
    assert gateway("inspect widget value") == "resolved:value"
    assert second.resolve() in gateway._sampler_routes
    assert first.resolve() not in gateway._sampler_routes


def test_sampler_fallback_rejects_equally_relevant_routes(tmp_path, monkeypatch):
    import pytest
    import gway.sampler as sampler

    _write_sampler_package(tmp_path, "alpha/widget", "def register(runtime):\n    pass\n")
    _write_sampler_package(tmp_path, "beta/widget", "def register(runtime):\n    pass\n")
    monkeypatch.setattr(sampler, "root", lambda: tmp_path)

    gateway = Gateway()

    with pytest.raises(LookupError, match="Ambiguous sampler fallback"):
        gateway("inspect widget value")


def test_missing_sampler_leaves_original_lookup_unresolved(tmp_path, monkeypatch):
    import pytest
    import gway.sampler as sampler

    missing = tmp_path / "missing"
    monkeypatch.setattr(sampler, "root", lambda: missing)

    gateway = Gateway()

    with pytest.raises(LookupError, match="Unable to resolve operation"):
        gateway("inspect widget value")
