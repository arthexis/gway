from gway import Gateway
from gway.documentation import render


def test_render_compact_help_uses_signature_and_summary():
    def deploy(target: str, force=False):
        """Deploy one target.

        Args:
            target: Deployment target name or address.
        """

    output = render(deploy)

    assert output == ("deploy(target: str, force=False)\nDeploy one target.")


def test_render_verbose_help_includes_docstring_and_parameter_facts():
    def deploy(target: str, force=False):
        """Deploy one target.

        Args:
            target: Deployment target name or address.
            force: Replace an existing deployment.
        """

    output = render(deploy, verbose=True)

    assert "Deploy one target." in output
    assert "  target\n" in output
    assert "    Deployment target name or address." in output
    assert "    Type: str" in output
    assert "    Required" in output
    assert "  force\n" in output
    assert "    Default: False" in output


def test_help_resolves_jit_ingested_builtin_operation(gateway):
    assert gateway.ops.resolve("log.config") is None

    output = gateway("help log config")

    assert gateway.ops.resolve("log.config") is not None
    assert output.startswith("log config(")
    assert "Inspect or configure one Python logger." in output
    assert "\nParameters:" not in output


def test_global_verbose_enables_full_help():
    gateway = Gateway(verbose=True)
    gateway.context.clear()
    gateway.context["verbose"] = True
    gateway.context["silent"] = False

    output = gateway("help log config")

    assert "Inspect or configure one Python logger." in output
    assert "\nParameters:" in output
    assert "  level\n" in output
    assert "  logger\n" in output


def test_explicit_help_verbose_overrides_runtime_default(gateway):
    output = gateway("help log config --verbose")

    assert "\nParameters:" in output


def test_help_handles_undocumented_parameter_mechanically(gateway):
    def inspect_target(target: str, retries=3):
        """Inspect one target."""

    gateway.inspect_target = gateway.wrap("inspect_target", inspect_target)

    output = gateway("help inspect_target --verbose")

    assert "  target\n" in output
    assert "    Type: str" in output
    assert "    Required" in output
    assert "  retries\n" in output
    assert "    Default: 3" in output


def test_help_preserves_receiver_adjusted_signature(gateway):
    class Device:
        def label(self, prefix: str):
            """Return a device label."""

    gateway.ingest(Device, path=("device",))

    output = gateway("help device label")

    assert output.startswith("device label(prefix: str)")
    assert "self" not in output


def test_builtin_install_help_explains_reconciliation_policy(gateway):
    output = gateway("help install --verbose")

    assert "Converge one local or Git artifact installation" in output
    assert "Replace an existing installation" in output
    assert "Discard drift in a dirty managed installation" in output
    assert "Preserve a dirty managed installation" in output


def test_builtin_test_run_help_explains_execution_filters(gateway):
    output = gateway("help test run --verbose")

    assert "Run tests through pytest" in output
    assert "Pytest -k expression" in output
    assert "last failures" in output


def test_builtin_log_config_help_explains_logger_target(gateway):
    output = gateway("help log config --verbose")

    assert "Logging threshold name or numeric value" in output
    assert "parent Gway logger" in output


def test_callable_log_level_has_subject_specific_summary(gateway):
    output = gateway("help log debug")

    assert "Log a DEBUG diagnostic" in output
    assert "callable and truth-testable" not in output


def test_verbose_help_does_not_duplicate_parameter_prose():
    def deploy(target: str):
        """Deploy one target.

        Args:
            target: Deployment target name or address.
        """

    output = render(deploy, verbose=True)

    assert output.count("Deployment target name or address.") == 1
    assert "Args:" not in output
    assert "Parameters:" in output


def test_cli_verbose_help_uses_structured_documentation(run_cli):
    status, output, _ = run_cli("-v", "help", "log", "config")

    assert status == 0
    assert "Inspect or configure one Python logger." in output
    assert "Parameters:" in output
    assert "Logging threshold name or numeric value" in output


def test_cli_verbose_interactive_uses_same_parameter_documentation(
    monkeypatch,
    run_cli,
):
    monkeypatch.setenv("GWAY_DOC_TEST", "documented-value")
    monkeypatch.setattr("builtins.input", lambda prompt: "GWAY_DOC_TEST")

    status, output, _ = run_cli("-i", "-v", "env")

    assert status == 0
    assert "name" in output
    assert "Environment variable name to read." in output
    assert "Required" in output
    assert "documented-value" in output


def test_help_supports_non_mutating_execution(gateway):
    output = gateway.execute("help log read", mutate=False)

    assert output.startswith("log read(")


def test_bare_help_lists_all_local_operations(gateway):
    output = gateway("help")

    assert "Available operations:" in output
    assert "log.read" in output
    assert "security.token.list" in output


def test_bare_help_does_not_expand_lazy_django_model_roots(gateway):
    from gway.ingestion.base import remember_object
    from gway.ingestion.django import ingest_model

    model = object()
    record = remember_object(
        gateway,
        model,
        ("charger",),
        expander=ingest_model,
    )

    output = gateway("help")

    assert "Available operations:" in output
    assert record.expanded is False


def test_bare_help_lists_only_authorized_operations(gateway):
    with gateway.authorized(operations={"help", "log.read"}):
        output = gateway("help")

    assert "help" in output
    assert "log.read" in output
    assert "security.whoami" in output
    assert "security.scope.current" in output
    assert "security.token.list" not in output
    assert "log.error" not in output


def test_namespace_help_filters_unauthorized_children(gateway):
    with gateway.authorized(operations={"help", "log.read"}):
        output = gateway("help log")

    assert "read" in output
    assert "error" not in output


def test_targeted_help_rejects_unauthorized_operation(gateway):
    with gateway.authorized(operations={"help", "log.read"}):
        import pytest

        with pytest.raises(LookupError, match="not available to current scope"):
            gateway("help security token list")
