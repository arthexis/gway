import pytest

from gway.ingestion.python import ingest_python


def test_ingested_controller_main_is_group_default(gateway):
    class Demo:
        def __main__(self, *, mutate=False):
            return ["one", "two"]

        def show(self, name):
            return name

    controller = Demo()
    ingest_python(gateway, controller, path=("demo", "group"))

    assert gateway("demo group") == ["one", "two"]
    assert gateway.ops.resolve("demo.group") is not None
    assert gateway("demo group show one") == "one"


def test_bare_group_without_main_returns_immediate_children(gateway):
    class Demo:
        def alpha(self):
            return "alpha"

        def beta(self):
            return "beta"

    ingest_python(gateway, Demo(), path=("demo", "tools"))

    result = gateway("demo tools")

    assert result["group"] == "demo tools"
    assert result["default"] is None
    assert [item["name"] for item in result["operations"]] == ["alpha", "beta"]
    assert all(item["command"].startswith("demo tools ") for item in result["operations"])


def test_namespace_fallback_does_not_consume_unknown_trailing_operation(gateway):
    class Demo:
        def alpha(self):
            return "alpha"

    ingest_python(gateway, Demo(), path=("demo", "tools"))

    with pytest.raises(LookupError, match="Unable to resolve operation"):
        gateway("demo tools missing")


def test_help_on_group_lists_children_even_when_group_has_default(gateway):
    class Demo:
        def __main__(self, *, mutate=False):
            return []

        def alpha(self):
            """Alpha operation."""
            return "alpha"

        def beta(self):
            """Beta operation."""
            return "beta"

    ingest_python(gateway, Demo(), path=("demo", "tools"))

    output = gateway("help demo tools")

    assert gateway.namespace("demo", "tools")["default"] == "demo tools"
    assert output.startswith("demo tools operations:")
    assert "alpha" in output
    assert "Alpha operation." in output
    assert "beta" in output
    assert "Bare 'demo tools' runs its group default." in output


def test_security_scope_bare_uses_list_default(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    gateway("security scope create logs")

    assert gateway("security scope") == gateway("security scope list")


def test_cli_group_help_uses_namespace_help(run_cli):
    status, output, _ = run_cli("security", "scope", "--help")

    assert status == 0
    assert "security scope operations:" in output
    assert "create" in output
    assert "delete" in output
    assert "list" in output
    assert "show" in output


def test_cli_bare_help_remains_global(run_cli):
    status, output, _ = run_cli("--help")

    assert status == 0
    assert "GWAY command-dispatch and composition core" in output
    assert "security scope operations:" not in output



def test_ingested_class_main_preserves_receiver_metadata(gateway):
    class Demo:
        def __main__(self):
            return "main"

        def show(self):
            return "show"

    ingest_python(gateway, Demo, path=("demo", "group"))

    default = gateway.ops.resolve("demo.group")
    assert default.__gway_receiver__ == "group"
    gateway.context["group"] = Demo()
    assert default() == "main"


@pytest.mark.parametrize(
    "args",
    [
        ("-r", "missing.rx", "--help"),
        ("-e", "missing operation", "--help"),
    ],
)
def test_cli_global_modes_keep_global_help(run_cli, args):
    status, output, _ = run_cli(*args)

    assert status == 0
    assert "GWAY command-dispatch and composition core" in output
    assert "security scope operations:" not in output


def test_cli_option_terminator_preserves_literal_trailing_help():
    from gway.console import _extract_command_help

    argv = ["echo", "--", "--help"]

    assert _extract_command_help(argv) == (False, argv)


def test_cli_command_help_resolves_operation_prefix(run_cli):
    status, output, _ = run_cli(
        "security",
        "scope",
        "show",
        "missing",
        "--help",
    )

    assert status == 0
    assert "security scope show" in output



def test_help_expands_lazy_namespace_on_first_call(gateway):
    class Child:
        def alpha(self):
            """Alpha operation."""
            return "alpha"

    class Root:
        pass

    root = Root()
    root.child = Child()
    ingest_python(gateway, root, path=("root",))

    output = gateway("help root child")

    assert output.startswith("root child operations:")
    assert "alpha" in output
    assert "Alpha operation." in output


def test_command_help_prefers_callable_prefix_over_argument_namespace(gateway):
    def foo(value):
        """Foo operation."""
        return value

    def baz():
        return "baz"

    gateway.wrap("foo", foo)
    gateway.wrap("foo.bar.baz", baz)

    assert gateway("foo bar") == "bar"

    output = gateway._command_help("foo", "bar")

    assert output.startswith("foo(value)")
    assert "Foo operation." in output
    assert "foo bar operations:" not in output



def test_namespace_direct_child_replaces_descendant_placeholder(gateway):
    def baz():
        return "baz"

    def bar():
        """Bar default operation."""
        return "bar"

    gateway.wrap("foo.bar.baz", baz)
    gateway.wrap("foo.bar", bar)

    info = gateway.namespace("foo")
    child = next(item for item in info["operations"] if item["name"] == "bar")

    assert child["group"] is True
    assert child["summary"] == "Bar default operation."


def test_command_group_help_preserves_humanized_name(gateway):
    def group():
        return "group"

    def child():
        return "child"

    gateway.wrap("demo.tools", group)
    gateway.wrap("demo.tools.child", child)

    output = gateway._command_help("demo", "tools")

    assert output.startswith("demo tools operations:")
    assert "demo.tools operations:" not in output
