import logging

import gway.logging as gway_logging
from gway import Gateway


def test_gateway_instances_use_unique_child_loggers():
    first = Gateway(name="worker")
    second = Gateway(name="worker")

    assert first.logger is not second.logger
    assert first.logger.name.startswith("gway.worker.")
    assert second.logger.name.startswith("gway.worker.")
    assert first.logger.parent.name == "gway"
    assert gway_logging.logger.name == "gway"
    assert gway_logging.logger.parent is logging.getLogger()


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


def test_logging_namespace_is_lazy_builtin(gateway, caplog):
    assert gateway.ops.resolve("gway.logging.info") is None

    with caplog.at_level(logging.INFO):
        assert gateway("gway logging info hello") is None

    assert gateway.ops.resolve("gway.logging.info") is not None
    assert any(record.getMessage() == "hello" for record in caplog.records)


def test_logging_namespace_exposes_selected_stdlib_functions(gateway):
    gateway("gway logging warning warning-message")

    for name in ("info", "warning", "error", "critical", "exception"):
        operation = gateway.ops.resolve(f"gway.logging.{name}")
        assert operation is not None
