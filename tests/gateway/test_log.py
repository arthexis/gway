from datetime import datetime, timezone
import logging
import gway.log as gway_log
from gway import Gateway
from gway.logs import LogRecord, LogSource
from gway.logs import operations as log_operations


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


def test_cli_log_level_controls_configured_output(
    run_cli,
    restore_gway_log_level,
):
    status, stdout, stderr = run_cli(
        "-L",
        "DEBUG",
        "--logfile",
        "stdout",
        "log",
        "debug",
        "cli-debug",
    )

    assert status == 0
    assert "DEBUG gway [gway] cli-debug" in stdout
    assert stderr == ""


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


def test_cli_restores_existing_output_handler(run_cli, tmp_path):
    previous = gway_log.configure_output(
        destination=tmp_path / "previous.log",
        level="WARNING",
    )
    previous_level = gway_log.logger.level
    previous_propagate = gway_log.logger.propagate

    try:
        status, _, _ = run_cli("log", "scoped-cli")
        assert status == 0
        assert gway_log.logger.level == previous_level
        assert gway_log.logger.propagate is previous_propagate
        assert previous in gway_log.logger.handlers
    finally:
        gway_log._remove_output_handler()
        gway_log.logger.setLevel(logging.WARNING)
        gway_log.logger.propagate = True



def test_log_query_operations_are_canonical_gateway_operations(gateway, monkeypatch):
    monkeypatch.setattr(log_operations, "sources", lambda: [{"identity": "gway"}])
    monkeypatch.setattr(
        log_operations,
        "read",
        lambda *source, **kwargs: [{"source": source[0] if source else "gway"}],
    )
    monkeypatch.setattr(
        log_operations,
        "tail",
        lambda *source, **kwargs: [{"source": source[0] if source else "gway"}],
    )
    monkeypatch.setattr(
        log_operations,
        "search",
        lambda pattern, *source, **kwargs: [
            {"source": source[0] if source else "gway", "message": pattern}
        ],
    )

    assert gateway("log sources") == [{"identity": "gway"}]
    assert gateway("log read gway") == [{"source": "gway"}]
    assert gateway("log tail gway --limit 20") == [{"source": "gway"}]
    assert gateway("log search timeout gway") == [
        {"source": "gway", "message": "timeout"}
    ]

    family = gateway.ops["log"]
    assert set(family) >= {"sources", "read", "tail", "search"}
    assert family["sources"].__gway_operation__ == "log"
    assert family["sources"].__gway_subject__ == "sources"
    assert family["read"].__gway_operation__ == "log"
    assert family["read"].__gway_subject__ == "read"
    assert family["tail"].__gway_subject__ == "tail"
    assert family["search"].__gway_subject__ == "search"


def test_log_read_returns_structured_serializable_records_through_gateway(
    gateway,
    monkeypatch,
):
    selected = LogSource(
        identity="gway",
        kind="gway",
        backend="journal",
        backend_id="gway",
    )
    monkeypatch.setattr(
        log_operations,
        "_query_groups",
        lambda requested: ([selected], []),
    )
    captured = {}

    def fake_journal(sources, **kwargs):
        captured["sources"] = list(sources)
        captured["kwargs"] = kwargs
        return [
            LogRecord(
                timestamp=datetime(
                    2026,
                    9,
                    22,
                    12,
                    0,
                    tzinfo=timezone.utc,
                ),
                source="gway",
                message="accepted",
                level="INFO",
                pid=42,
                unit=None,
            )
        ]

    monkeypatch.setattr(log_operations, "read_journal", fake_journal)

    result = gateway("log read gway --limit 10")

    assert [source.identity for source in captured["sources"]] == ["gway"]
    assert captured["kwargs"]["limit"] == 10
    assert result == [
        {
            "timestamp": "2026-09-22T12:00:00+00:00",
            "source": "gway",
            "level": "INFO",
            "message": "accepted",
            "pid": 42,
            "unit": None,
        }
    ]


def test_log_empty_selection_never_means_whole_host_journal(gateway, monkeypatch):
    captured = {}

    def fake_read(*source, **kwargs):
        captured["source"] = source
        return []

    monkeypatch.setattr(log_operations, "read", fake_read)

    assert gateway("log read") == []
    assert captured["source"] == ()



def test_log_query_operations_support_non_mutating_gateway_execution(
    gateway,
    monkeypatch,
):
    monkeypatch.setattr(log_operations, "sources", lambda: [{"identity": "gway"}])
    monkeypatch.setattr(
        log_operations,
        "read",
        lambda *source, **kwargs: [{"source": source[0] if source else "gway"}],
    )
    monkeypatch.setattr(
        log_operations,
        "tail",
        lambda *source, **kwargs: [{"source": source[0] if source else "gway"}],
    )
    monkeypatch.setattr(
        log_operations,
        "search",
        lambda pattern, *source, **kwargs: [{"message": pattern}],
    )

    assert gateway.execute("log sources", mutate=False) == [{"identity": "gway"}]
    assert gateway.execute("log read gway", mutate=False) == [{"source": "gway"}]
    assert gateway.execute("log tail gway --limit 1", mutate=False) == [
        {"source": "gway"}
    ]
    assert gateway.execute("log search timeout gway", mutate=False) == [
        {"message": "timeout"}
    ]

    family = gateway.ops["log"]
    for name in ("sources", "read", "tail", "search"):
        assert family[name].mutates is False
