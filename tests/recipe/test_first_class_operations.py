import inspect

import pytest

from gway import Gateway
from gway.dispatch import resolve_operation
from gway.tokens import tokenize


def _write(path, content=""):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _root_gateway(tmp_path):
    gateway = Gateway()
    root = tmp_path / "ops"
    root.mkdir()
    gateway.add_operation_root(root)
    return gateway, root


def test_root_recipe_becomes_first_class_operation(tmp_path, monkeypatch):
    gateway, root = _root_gateway(tmp_path)
    recipe = _write(root / "greet.rx", "version\n")
    calls = []

    def fake_execute(runtime, path, *, context=None, **kwargs):
        calls.append((path, dict(context or {})))
        return [], "recipe-body"

    monkeypatch.setattr("gway.recipe.operation.execute_recipe", fake_execute)

    assert gateway("greet") == "recipe-body"
    assert calls == [(recipe.resolve(), {})]
    operation = gateway.ops.resolve("greet")
    assert getattr(operation, "__gway_source_kind__", None) == "recipe"


def test_directory_main_recipe_is_bare_operation_and_children_are_qualified(
    tmp_path,
    monkeypatch,
):
    gateway, root = _root_gateway(tmp_path)
    main = _write(root / "watch" / "__main__.rx", "version\n")
    service = _write(root / "watch" / "service.rx", "version\n")
    calls = []

    def fake_execute(runtime, path, *, context=None, **kwargs):
        calls.append(path)
        return [], path.name

    monkeypatch.setattr("gway.recipe.operation.execute_recipe", fake_execute)

    assert gateway("watch") == "__main__.rx"
    assert gateway("watch service") == "service.rx"
    assert calls == [main.resolve(), service.resolve()]

    bare = gateway.ops._registry.records["watch"]
    child = gateway.ops._registry.records["watch.service"]
    assert bare.sub is None
    assert child.op == "service"
    assert child.sub == "watch"


def test_directory_family_does_not_publish_deeper_internal_recipes(tmp_path):
    gateway, root = _root_gateway(tmp_path)
    _write(root / "watch" / "__main__.rx", "version\n")
    _write(root / "watch" / "internal" / "secret.rx", "version\n")

    resolve_operation(gateway, tokenize("watch"))

    assert gateway.ops.resolve("watch") is not None
    assert gateway.ops.resolve("watch.internal.secret") is None


def test_companion_main_projects_public_contract_without_becoming_implementation(
    tmp_path,
    monkeypatch,
):
    gateway, root = _root_gateway(tmp_path)
    recipe = _write(root / "greet.rx", "version\n")
    _write(
        root / "greet.py",
        '''
def __main__(name: str = "world", *, loud=False, mutate=False):
    """Return a greeting from the recipe."""
    raise AssertionError("__main__ is metadata only")
''',
    )
    observed = []

    def fake_execute(runtime, path, *, context=None, **kwargs):
        observed.append((path, dict(context or {})))
        return [], context["name"]

    monkeypatch.setattr("gway.recipe.operation.execute_recipe", fake_execute)

    resolution = resolve_operation(gateway, tokenize("greet"))
    signature = inspect.signature(resolution.callable)

    assert tuple(signature.parameters) == ("name", "loud")
    assert resolution.callable.__doc__ == "Return a greeting from the recipe."
    assert resolution.callable.mutates is False
    assert gateway("greet Alice") == "Alice"
    assert observed == [(recipe.resolve(), {"name": "Alice", "loud": False})]


def test_directory_main_companion_projects_contract(tmp_path, monkeypatch):
    gateway, root = _root_gateway(tmp_path)
    recipe = _write(root / "watch" / "__main__.rx", "version\n")
    _write(
        root / "watch" / "__main__.py",
        '''
def __main__(since=None, *, mutate=False):
    """Watch this node."""
''',
    )

    monkeypatch.setattr(
        "gway.recipe.operation.execute_recipe",
        lambda runtime, path, *, context=None, **kwargs: ([], context),
    )

    resolution = resolve_operation(gateway, tokenize("watch"))
    assert tuple(inspect.signature(resolution.callable).parameters) == ("since",)
    assert resolution.callable.__doc__ == "Watch this node."
    assert resolution.callable.mutates is False
    assert gateway("watch 1h") == {"since": "1h"}


def test_same_route_rejects_file_and_directory_main_collision(tmp_path):
    gateway, root = _root_gateway(tmp_path)
    _write(root / "watch.rx", "version\n")
    _write(root / "watch" / "__main__.rx", "version\n")

    with pytest.raises(LookupError, match="Ambiguous first-class recipe"):
        resolve_operation(gateway, tokenize("watch"))
