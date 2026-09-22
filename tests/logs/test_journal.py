import json
import subprocess

import pytest

from gway.logs import LogSource
from gway.logs.journal import (
    JournalError,
    _build_command,
    _parse_output,
    read_journal,
)


def source(identity, unit, *, system=False):
    project, service = identity.split("/", 1)
    return LogSource(
        identity=identity,
        kind="service",
        project=project,
        service=service,
        backend="systemd",
        backend_id=unit,
        system=system,
    )


def entry(unit, micros, message, *, priority="6", pid="42"):
    return json.dumps(
        {
            "__REALTIME_TIMESTAMP": str(micros),
            "_SYSTEMD_UNIT": unit,
            "MESSAGE": message,
            "PRIORITY": priority,
            "_PID": pid,
        }
    )


def test_build_command_uses_persisted_units_without_shell_interpolation():
    sources = [
        source("arthexis/web", "custom-web.service"),
        source("arthexis/worker", "custom-worker.service"),
    ]

    command = _build_command(
        sources,
        system=False,
        since="10 minutes ago",
        until="now",
        limit=50,
        grep="connection refused",
        reverse=True,
    )

    assert command == [
        "journalctl",
        "--user",
        "--output=json",
        "--no-pager",
        "--unit=custom-web.service",
        "--unit=custom-worker.service",
        "--since",
        "10 minutes ago",
        "--until",
        "now",
        "--lines=50",
        "--grep",
        "connection refused",
        "--reverse",
    ]


def test_parse_output_normalizes_and_attributes_multiple_units():
    sources = [
        source("arthexis/web", "arthexis-web.service"),
        source("arthexis/worker", "arthexis-worker.service"),
    ]
    output = "\n".join(
        [
            entry(
                "arthexis-web.service",
                1_700_000_000_000_000,
                "request complete",
                priority="6",
                pid="101",
            ),
            entry(
                "arthexis-worker.service",
                1_700_000_001_000_000,
                "job failed",
                priority="3",
                pid="202",
            ),
        ]
    )

    records = _parse_output(output, sources)

    assert [record.source for record in records] == [
        "arthexis/web",
        "arthexis/worker",
    ]
    assert records[0].message == "request complete"
    assert records[0].level == "INFO"
    assert records[0].pid == 101
    assert records[1].level == "ERROR"
    assert records[1].metadata["journal_priority"] == 3


def test_single_source_can_attribute_entry_without_unit_field():
    selected = [source("arthexis/web", "arthexis-web.service")]
    output = json.dumps(
        {
            "__REALTIME_TIMESTAMP": "1700000000000000",
            "MESSAGE": "hello",
        }
    )

    records = _parse_output(output, selected)

    assert records[0].source == "arthexis/web"
    assert records[0].unit is None


def test_multiple_sources_require_attributable_unit():
    selected = [
        source("arthexis/web", "arthexis-web.service"),
        source("arthexis/worker", "arthexis-worker.service"),
    ]
    output = json.dumps(
        {
            "__REALTIME_TIMESTAMP": "1700000000000000",
            "MESSAGE": "ambiguous",
        }
    )

    with pytest.raises(JournalError, match="cannot be attributed"):
        _parse_output(output, selected)


def test_read_journal_groups_user_and_system_scopes(monkeypatch):
    calls = []
    user = source("arthexis/web", "arthexis-web.service", system=False)
    system = source("infra/watch", "infra-watch.service", system=True)

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        unit = next(value.split("=", 1)[1] for value in command if value.startswith("--unit="))
        micros = (
            1_700_000_000_000_000
            if "--user" in command
            else 1_700_000_001_000_000
        )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=entry(unit, micros, unit),
            stderr="",
        )

    monkeypatch.setattr("gway.logs.journal.subprocess.run", fake_run)

    records = read_journal([system, user], limit=10)

    assert len(calls) == 2
    assert "--user" in calls[0][0]
    assert "--user" not in calls[1][0]
    assert all(call[1]["check"] is True for call in calls)
    assert [record.source for record in records] == [
        "arthexis/web",
        "infra/watch",
    ]


def test_read_journal_uses_one_query_for_multiple_sources_same_scope(monkeypatch):
    calls = []
    sources = [
        source("arthexis/web", "arthexis-web.service"),
        source("arthexis/worker", "arthexis-worker.service"),
    ]

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout="\n".join(
                [
                    entry("arthexis-web.service", 1_700_000_000_000_000, "web"),
                    entry(
                        "arthexis-worker.service",
                        1_700_000_001_000_000,
                        "worker",
                    ),
                ]
            ),
            stderr="",
        )

    monkeypatch.setattr("gway.logs.journal.subprocess.run", fake_run)

    records = read_journal(sources)

    assert len(calls) == 1
    assert "--unit=arthexis-web.service" in calls[0]
    assert "--unit=arthexis-worker.service" in calls[0]
    assert [record.source for record in records] == [
        "arthexis/web",
        "arthexis/worker",
    ]


def test_read_journal_rejects_aggregate_and_non_systemd_sources():
    with pytest.raises(ValueError, match="concrete service"):
        read_journal([LogSource(identity="arthexis", kind="project")])

    with pytest.raises(ValueError, match="not systemd-backed"):
        read_journal(
            [
                LogSource(
                    identity="arthexis/web",
                    kind="service",
                    backend="process",
                    backend_id="web",
                    system=False,
                )
            ]
        )


def test_read_journal_wraps_process_failure(monkeypatch):
    selected = [source("arthexis/web", "arthexis-web.service")]

    def fail(command, **kwargs):
        raise subprocess.CalledProcessError(
            1,
            command,
            stdout="",
            stderr="permission denied",
        )

    monkeypatch.setattr("gway.logs.journal.subprocess.run", fail)

    with pytest.raises(JournalError, match="permission denied") as raised:
        read_journal(selected)

    assert raised.value.returncode == 1
    assert raised.value.stderr == "permission denied"


def test_read_journal_wraps_timeout(monkeypatch):
    selected = [source("arthexis/web", "arthexis-web.service")]

    def fail(command, **kwargs):
        raise subprocess.TimeoutExpired(command, 40, stderr=b"too slow")

    monkeypatch.setattr("gway.logs.journal.subprocess.run", fail)

    with pytest.raises(JournalError, match="timed out") as raised:
        read_journal(selected)

    assert raised.value.timeout == 40
    assert raised.value.stderr == "too slow"


def test_read_journal_wraps_missing_journalctl(monkeypatch):
    selected = [source("arthexis/web", "arthexis-web.service")]

    def fail(command, **kwargs):
        raise FileNotFoundError("journalctl")

    monkeypatch.setattr("gway.logs.journal.subprocess.run", fail)

    with pytest.raises(JournalError, match="not available"):
        read_journal(selected)
