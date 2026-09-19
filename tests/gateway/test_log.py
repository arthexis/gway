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


def test_verbose_and_silent_are_runtime_logger_properties(gateway):
    assert gateway.verbose is False
    assert gateway.silent is False
    assert gateway.logger.level == logging.NOTSET

    gateway.verbose = True
    assert gateway.logger.level == logging.INFO

    gateway.silent = True
    assert gateway.logger.level > logging.CRITICAL

    gateway.silent = False
    assert gateway.logger.level == logging.INFO

    gateway.verbose = False
    assert gateway.logger.level == logging.NOTSET


def test_log_dunder_main_is_default_operation(gateway, caplog):
    assert gateway.ops.resolve("gway.log") is None

    with caplog.at_level(logging.INFO):
        assert gateway("gway log hello") is None

    assert gateway.ops.resolve("gway.log") is not None
    assert any(record.getMessage() == "hello" for record in caplog.records)


def test_log_dunder_main_supports_explicit_level(gateway, caplog):
    with caplog.at_level(logging.WARNING):
        assert gateway("gway log hello --level 30") is None

    assert any(
        record.getMessage() == "hello" and record.levelno == logging.WARNING
        for record in caplog.records
    )


def test_log_subjects_are_jit_ingested(gateway, caplog):
    assert gateway.ops.resolve("gway.log.info") is None

    with caplog.at_level(logging.INFO):
        assert gateway("gway log info hello") is None

    assert gateway.ops.resolve("gway.log.info") is not None
    assert any(record.getMessage() == "hello" for record in caplog.records)


def test_log_family_uses_operation_and_subject_semantics(gateway):
    gateway("gway log info hello")
    gateway("gway log warning warning-message")
    gateway("gway log warn warn-message")

    family = gateway.ops["log"]

    assert family[None].__wrapped__ is gway_log.__main__
    assert family["info"].__wrapped__ is gway_log.info
    assert family["warning"].__wrapped__ is gway_log.warning
    assert family["warn"].__wrapped__ is gway_log.warn

    assert gateway.subs["info"]["log"] is family["info"]
    assert gateway.subs["warning"]["log"] is family["warning"]
    assert gateway.subs["warn"]["log"] is family["warn"]


def test_log_exposes_standard_level_subjects(gateway):
    gateway("gway log info hello")

    family = gateway.ops["log"]
    for subject in (
        "debug",
        "info",
        "warning",
        "warn",
        "error",
        "critical",
        "exception",
    ):
        assert subject in family
