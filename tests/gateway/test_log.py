import logging
import gway.log as gway_log
from gway import Gateway


def test_gateway_instances_use_unique_child_loggers():
    first = Gateway(name="worker")
    second = Gateway(name="worker")

    assert first.logger is not second.logger
    assert first.logger.name.startswith("gway.worker.")
    assert second.logger.name.startswith("gway.worker.")
    assert first.logger.parent.name == "gway"
    assert gway_log.logger.name == "gway"
    assert gway_log.logger.parent is logging.getLogger()


def test_gateway_log_levels_are_callable_and_boolean():
    gateway = Gateway(log_level="WARNING")

    assert bool(gateway.debug) is False
    assert bool(gateway.info) is False
    assert bool(gateway.warning) is True
    assert bool(gateway.error) is True
    assert gateway.warn is gateway.warning


def test_gateway_log_level_can_change_without_changing_output_intent():
    gateway = Gateway(verbose=True, silent=True, log_level="DEBUG")

    assert gateway.verbose is True
    assert gateway.silent is True
    assert bool(gateway.debug) is True

    gateway.logger.setLevel(logging.ERROR)

    assert gateway.verbose is True
    assert gateway.silent is True
    assert bool(gateway.info) is False
    assert bool(gateway.error) is True


def test_verbose_and_silent_are_semantic_output_intent():
    gateway = Gateway(verbose=True, silent=True)

    def intent(verbose=False, silent=False):
        return verbose, silent

    gateway.intent = gateway.wrap("intent", intent)

    assert gateway("intent") == (True, True)


def test_log_config_changes_parent_level_and_boolean_levels(restore_gway_log_level):
    gateway = Gateway()
    configured = gateway("log config --level INFO")

    assert configured["logger"] == "gway"
    assert configured["level"] == "INFO"
    assert bool(gateway.info) is True
    assert bool(gateway.debug) is False


def test_log_config_can_target_another_python_logger():
    target = logging.getLogger("gway-test.external")
    previous = target.level
    gateway = Gateway()
    try:
        configured = gateway("log config --level ERROR --logger gway-test.external")

        assert configured["logger"] == "gway-test.external"
        assert configured["level"] == "ERROR"
        assert target.level == logging.ERROR
    finally:
        target.setLevel(previous)


def test_log_dunder_main_is_default_operation(gateway, caplog):
    assert gateway.ops.resolve("log") is None

    with caplog.at_level(logging.INFO, logger="gway"):
        assert gateway("log hello") is None

    assert gateway.ops.resolve("log") is not None
    assert any(record.getMessage() == "hello" for record in caplog.records)


def test_log_dunder_main_supports_explicit_level(gateway, caplog):
    with caplog.at_level(logging.WARNING, logger="gway"):
        assert gateway("log hello --level 30") is None

    assert any(
        record.getMessage() == "hello" and record.levelno == logging.WARNING
        for record in caplog.records
    )


def test_log_subjects_are_jit_ingested(gateway, caplog):
    assert gateway.ops.resolve("log.info") is None

    with caplog.at_level(logging.INFO, logger="gway"):
        assert gateway("log info hello") is None

    assert gateway.ops.resolve("log.info") is not None
    assert any(record.getMessage() == "hello" for record in caplog.records)


def test_log_exposes_standard_levels_and_config(gateway):
    gateway("log info hello")

    family = gateway.ops["log"]
    assert set(family) >= {
        "debug",
        "info",
        "warning",
        "warn",
        "error",
        "critical",
        "exception",
        "config",
    }
    assert family["warn"].__wrapped__ is family["warning"].__wrapped__


def test_cli_log_level_controls_gway_logger_hierarchy(
    run_cli,
    caplog,
    restore_gway_log_level,
):
    with caplog.at_level(logging.DEBUG):
        status, _, _ = run_cli("-L", "DEBUG", "log", "debug", "cli-debug")

    assert status == 0
    assert any(
        record.getMessage() == "cli-debug" and record.levelno == logging.DEBUG
        for record in caplog.records
    )


def test_cli_silent_suppresses_result_without_changing_log_level(
    monkeypatch,
    run_cli,
    restore_gway_log_level,
):
    gway_log.logger.setLevel(logging.WARNING)
    monkeypatch.setenv("GWAY_SILENT_RESULT", "visible")

    status, stdout, _ = run_cli(
        "--silent",
        "env",
        "GWAY_SILENT_RESULT",
    )

    assert status == 0
    assert stdout == ""
    assert gway_log.logger.level == logging.WARNING
