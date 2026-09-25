import json
import pytest

from gway.logs import LogSource
from gway.logs.file import FileLogError, log_files, read_file_logs


def _source(identity, *, system=False):
    project, service = identity.split("/", 1)
    return LogSource(
        identity=identity,
        kind="service",
        project=project,
        service=service,
        backend="process",
        backend_id=service,
        system=system,
    )


def _row(timestamp, source_name, message, *, level="INFO", pid=1):
    return json.dumps(
        {
            "timestamp": timestamp,
            "level": level,
            "logger": "gway",
            "source": source_name,
            "message": message,
            "pid": pid,
            "unit": None,
        }
    )


def test_log_files_orders_rotated_before_current(tmp_path):
    base = tmp_path / "gway.log"
    (tmp_path / "gway.log.2026-09-20").write_text("", encoding="utf-8")
    (tmp_path / "gway.log.2026-09-21").write_text("", encoding="utf-8")
    base.write_text("", encoding="utf-8")

    assert log_files(base) == [
        tmp_path / "gway.log.2026-09-20",
        tmp_path / "gway.log.2026-09-21",
        base,
    ]


def test_read_file_logs_round_trips_structured_records(tmp_path):
    base = tmp_path / "gway.log"
    base.write_text(
        "\n".join(
            [
                _row(
                    "2026-09-22T10:00:00+00:00",
                    "arthexis/web",
                    "first",
                    pid=10,
                ),
                _row(
                    "2026-09-22T11:00:00+00:00",
                    "arthexis/worker",
                    "second",
                    level="ERROR",
                    pid=20,
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    records = read_file_logs(
        [
            _source("arthexis/web"),
            _source("arthexis/worker"),
        ],
        paths=[base],
    )

    assert [record.source for record in records] == [
        "arthexis/web",
        "arthexis/worker",
    ]
    assert records[0].timestamp.tzinfo is not None
    assert records[0].pid == 10
    assert records[1].level == "ERROR"


def test_read_file_logs_filters_source_time_and_regex(tmp_path):
    base = tmp_path / "gway.log"
    base.write_text(
        "\n".join(
            [
                _row("2026-09-22T09:00:00+00:00", "arthexis/web", "old timeout"),
                _row("2026-09-22T10:00:00+00:00", "arthexis/web", "healthy"),
                _row("2026-09-22T11:00:00+00:00", "arthexis/web", "new timeout"),
                _row("2026-09-22T12:00:00+00:00", "arthexis/worker", "worker timeout"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    records = read_file_logs(
        [_source("arthexis/web")],
        paths=[base],
        since="2026-09-22T09:30:00+00:00",
        until="2026-09-22T11:30:00+00:00",
        grep="timeout",
    )

    assert [record.message for record in records] == ["new timeout"]


def test_read_limit_keeps_newest_window_in_chronological_order(tmp_path):
    base = tmp_path / "gway.log"
    base.write_text(
        "\n".join(
            [
                _row("2026-09-22T09:00:00+00:00", "arthexis/web", "oldest"),
                _row("2026-09-22T10:00:00+00:00", "arthexis/web", "new"),
                _row("2026-09-22T11:00:00+00:00", "arthexis/web", "newest"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    records = read_file_logs(
        [_source("arthexis/web")],
        paths=[base],
        limit=2,
    )

    assert [record.message for record in records] == ["new", "newest"]


def test_tail_reverse_and_limit_apply_globally_across_rotations(tmp_path):
    base = tmp_path / "gway.log"
    rotated = tmp_path / "gway.log.2026-09-21"
    rotated.write_text(
        _row("2026-09-21T23:00:00+00:00", "arthexis/web", "older") + "\n",
        encoding="utf-8",
    )
    base.write_text(
        "\n".join(
            [
                _row("2026-09-22T10:00:00+00:00", "arthexis/web", "new"),
                _row("2026-09-22T11:00:00+00:00", "arthexis/web", "newest"),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    records = read_file_logs(
        [_source("arthexis/web")],
        paths=[base],
        reverse=True,
        limit=2,
    )

    assert [record.message for record in records] == ["newest", "new"]


def test_legacy_text_rows_are_ignored_during_migration(tmp_path):
    base = tmp_path / "gway.log"
    base.write_text(
        "2026-09-21 INFO gway [gway] legacy\n"
        + _row("2026-09-22T10:00:00+00:00", "arthexis/web", "structured")
        + "\n",
        encoding="utf-8",
    )

    records = read_file_logs([_source("arthexis/web")], paths=[base])

    assert [record.message for record in records] == ["structured"]


def test_truncated_active_final_json_row_is_ignored(tmp_path):
    base = tmp_path / "gway.log"
    base.write_text(
        _row("2026-09-22T10:00:00+00:00", "arthexis/web", "complete")
        + "\n"
        + '{"timestamp":"2026-09-22T11:00:00+00:00"',
        encoding="utf-8",
    )

    records = read_file_logs([_source("arthexis/web")], paths=[base])

    assert [record.message for record in records] == ["complete"]


def test_malformed_complete_json_row_fails_clearly(tmp_path):
    base = tmp_path / "gway.log"
    base.write_text("{bad json}\n", encoding="utf-8")

    with pytest.raises(FileLogError, match="invalid structured log JSON"):
        read_file_logs([_source("arthexis/web")], paths=[base])


def test_file_time_bounds_require_iso_timestamps(tmp_path):
    base = tmp_path / "gway.log"
    base.write_text("", encoding="utf-8")

    with pytest.raises(FileLogError, match="ISO-8601 or a supported relative time"):
        read_file_logs(
            [_source("arthexis/web")],
            paths=[base],
            since="sometime later",
        )


def test_file_time_bounds_support_common_relative_syntax(tmp_path):
    base = tmp_path / "gway.log"
    base.write_text(
        _row("2000-01-01T00:00:00+00:00", "arthexis/web", "ancient") + "\n",
        encoding="utf-8",
    )

    records = read_file_logs(
        [_source("arthexis/web")],
        paths=[base],
        since="10 minutes ago",
    )

    assert records == []
