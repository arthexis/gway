import inspect

import pytest

from gway import Gateway
from gway.dispatch import resolve_operation
from gway.documentation import describe
from gway.mutation import MutationError
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
    _write(root / "watch" / "__main__.rx", "version\n")
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


def test_recipe_operation_uses_normal_documentation_surface(tmp_path):
    gateway, root = _root_gateway(tmp_path)
    _write(root / "greet.rx", "version\n")
    _write(
        root / "greet.py",
        '''
def __main__(name: str, *, punctuation="!", mutate=False):
    """Return a greeting.

    Args:
        name: Person to greet.
        punctuation: Suffix for the greeting.
    """
''',
    )

    operation = resolve_operation(gateway, tokenize("greet")).callable
    documentation = describe(operation)

    assert documentation.summary == "Return a greeting."
    assert documentation.source_kind == "recipe"
    assert documentation.path == ("greet",)
    assert tuple(documentation.signature.parameters) == ("name", "punctuation")
    assert documentation.parameter("name").required is True
    assert documentation.parameter("name").description == "Person to greet."
    assert documentation.parameter("punctuation").default == "!"
    assert documentation.parameter("punctuation").description == (
        "Suffix for the greeting."
    )
    assert "Return a greeting." in gateway._command_help("greet", verbose=True)


def test_recipe_operation_participates_in_normal_chaining(tmp_path):
    gateway, root = _root_gateway(tmp_path)
    _write(root / "greet.rx", "version\n")

    gateway.wrap("echo", lambda value=None: value)
    result = gateway("greet - echo")

    assert result == gateway("version")


def test_non_mutating_recipe_respects_outer_no_mutate_for_child_operations(tmp_path):
    gateway, root = _root_gateway(tmp_path)
    _write(root / "inspect.rx", "danger\n")
    _write(
        root / "inspect.py",
        """
def __main__(*, mutate=False):
    \"\"\"Observe without mutation.\"\"\"
""",
    )
    calls = []

    def danger():
        calls.append("danger")
        return "changed"

    gateway.wrap("danger", danger)

    with pytest.raises(MutationError, match="does not support non-mutating execution"):
        gateway.execute("inspect", mutate=False)

    assert calls == []


def test_recipe_without_non_mutating_contract_is_conservatively_mutating(tmp_path):
    gateway, root = _root_gateway(tmp_path)
    _write(root / "legacy.rx", "version\n")

    operation = resolve_operation(gateway, tokenize("legacy")).callable

    assert operation.mutates is True


def test_authorized_external_execution_accepts_recipe_operation_name(tmp_path):
    gateway, root = _root_gateway(tmp_path)
    _write(root / "inspect.rx", "version\n")
    _write(
        root / "inspect.py",
        """
def __main__(*, mutate=False):
    \"\"\"Return an observation.\"\"\"
""",
    )

    expected = gateway("version")
    with gateway.authorized(operations={"inspect"}):
        assert gateway("inspect") == expected


def test_external_authority_cannot_configure_operation_roots(tmp_path):
    gateway = Gateway()

    with gateway.authorized(operations={"__all__"}):
        assert gateway.ops.resolve("root") is None
        assert gateway.ops.resolve("add.root") is None


def test_registered_operation_precedes_explicit_root(tmp_path):
    gateway, root = _root_gateway(tmp_path)
    _write(root / "status.rx", "version\n")
    gateway.wrap("status", lambda: "registered")

    assert gateway("status") == "registered"


def test_explicit_root_precedes_sampler_first_class_recipe(tmp_path, monkeypatch):
    import gway.sampler as sampler

    explicit = tmp_path / "explicit"
    maintained = tmp_path / "sampler"
    explicit.mkdir()
    maintained.mkdir()
    _write(explicit / "status.rx", "version\n")
    _write(maintained / "status.rx", "version\n")

    monkeypatch.setattr(sampler, "root", lambda: maintained)
    gateway = Gateway()
    gateway.add_operation_root(explicit)

    operation = resolve_operation(gateway, tokenize("status")).callable

    assert operation.__gway_metadata__["root"] == explicit.resolve()


def test_first_explicit_root_precedes_later_root_for_recipe_operation(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    _write(first / "status.rx", "version\n")
    _write(second / "status.rx", "version\n")

    gateway = Gateway()
    gateway.add_operation_root(first)
    gateway.add_operation_root(second)

    operation = resolve_operation(gateway, tokenize("status")).callable

    assert operation.__gway_metadata__["root"] == first.resolve()


def test_leading_recipe_comments_become_help_without_companion(tmp_path):
    gateway, root = _root_gateway(tmp_path)
    _write(
        root / "inspect.rx",
        """# Inspect the current node.
#
# Returns a bounded observation snapshot.

version
# Internal implementation note.
""",
    )

    output = gateway("help inspect --verbose")

    assert "Inspect the current node." in output
    assert "Returns a bounded observation snapshot." in output
    assert "Internal implementation note." not in output


def test_companion_main_docstring_overrides_leading_recipe_help(tmp_path):
    gateway, root = _root_gateway(tmp_path)
    _write(root / "inspect.rx", "# Recipe comment help.\nversion\n")
    _write(
        root / "inspect.py",
        '''
def __main__(*, mutate=False):
    """Companion main help."""
''',
    )

    output = gateway("help inspect")

    assert "Companion main help." in output
    assert "Recipe comment help." not in output


def test_static_dunder_help_augments_and_overrides_recipe_help(tmp_path):
    gateway, root = _root_gateway(tmp_path)
    _write(root / "watch.rx", "# Native watch help.\nversion\n")
    _write(
        root / "watch.py",
        '''
def __main__(since=None, *, mutate=False):
    """Main watch documentation.

    Args:
        since: Mechanical since description.
    """

def __help__(topic=None):
    return {
        "summary": "Observe this node.",
        "description": "Build a stable bounded node snapshot.",
        "examples": ["gway watch", "gway watch --since 1h"],
        "notes": ["Read-only by contract."],
        "--since": {
            "summary": "Recent observations",
            "description": "Limit time-aware observations to a recent window.",
            "examples": ["gway watch --since 30m"],
        },
        "services stale": {
            "description": "Explain stale managed service observations."
        },
    }
''',
    )

    compact = gateway("help watch")
    verbose = gateway("help watch --verbose")
    since = gateway("help watch --since")
    conceptual = gateway("help watch services stale")

    assert "Observe this node." in compact
    assert "Build a stable bounded node snapshot." in verbose
    assert "Examples:" in verbose
    assert "gway watch --since 1h" in verbose
    assert "Notes:" in verbose
    assert "Recent observations" in since
    assert "Limit time-aware observations" in since
    assert "gway watch --since 30m" in since
    assert "Explain stale managed service observations." in conceptual


def test_dunder_help_can_use_explicit_topics_mapping_and_none_general_entry(tmp_path):
    gateway, root = _root_gateway(tmp_path)
    _write(root / "probe.rx", "version\n")
    _write(
        root / "probe.py",
        '''
def __main__(target=None, *, mutate=False):
    pass

def __help__(topic=None):
    return {
        None: {
            "summary": "Probe something.",
            "description": "General probe documentation.",
        },
        "topics": {
            "target": "Select the target to probe.",
            "behavior details": {
                "summary": "Behavior",
                "description": "Detailed behavior documentation.",
            },
        },
    }
''',
    )

    assert "Probe something." in gateway("help probe")
    assert "Select the target to probe." in gateway("help probe target")
    assert "Detailed behavior documentation." in gateway(
        "help probe behavior details"
    )


def test_dunder_help_is_special_metadata_not_a_callable_operation(tmp_path):
    gateway, root = _root_gateway(tmp_path)
    _write(root / "watch.rx", "version\n")
    _write(
        root / "watch.py",
        '''
def __main__(*, mutate=False):
    pass

def __help__():
    return {"summary": "Watch help."}
''',
    )

    resolve_operation(gateway, tokenize("watch"))

    assert gateway.ops.resolve("watch") is not None
    assert gateway.ops.resolve("watch.__help__") is None
    assert gateway.ops.resolve("__help__") is None


def test_specific_parameter_help_falls_back_to_signature_and_docstring(tmp_path):
    gateway, root = _root_gateway(tmp_path)
    _write(root / "greet.rx", "version\n")
    _write(
        root / "greet.py",
        '''
def __main__(name: str, *, punctuation="!", mutate=False):
    """Return a greeting.

    Args:
        name: Person to greet.
        punctuation: Ending punctuation.
    """
''',
    )

    output = gateway("help greet --punctuation")

    assert output.startswith("punctuation")
    assert "Ending punctuation." in output
    assert "Default: '!'" in output
