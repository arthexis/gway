from datetime import datetime, timezone

import pytest

from gway.install.service import ServiceInstallRecord, ServiceInstallState
from gway.logs import LogRecord
from gway.logs import operations


@pytest.fixture
def catalog_state(tmp_path, monkeypatch):
    state = ServiceInstallState(tmp_path)
    state.put("arthexis", [
        ServiceInstallRecord(project="arthexis", service="web", backend_id="arthexis-web.service", backend="systemd", system=False),
        ServiceInstallRecord(project="arthexis", service="worker", backend_id="arthexis-worker.service", backend="systemd", system=False),
        ServiceInstallRecord(project="arthexis", service="portable", backend_id="portable", backend="process", system=False),
    ])
    monkeypatch.setattr(operations, "_install_state", lambda: state)
    monkeypatch.setattr(operations, "_journal_available", lambda: True)
    return state


def record(source="gway"):
    return LogRecord(
        timestamp=datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
        source=source,
        message="hello",
        level="INFO",
        pid=42,
        unit=None,
        metadata={"SECRET": "hidden"},
    )


def test_sources_returns_serializable_catalog(catalog_state):
    result = operations.sources()
    assert [item["identity"] for item in result] == [
        "gway", "arthexis", "arthexis/portable", "arthexis/web", "arthexis/worker"
    ]


def test_read_expands_project_to_readable_members(catalog_state, monkeypatch):
    captured = {}
    def fake_read(sources, **kwargs):
        captured["sources"] = sources
        captured["kwargs"] = kwargs
        return [record("arthexis/web")]
    monkeypatch.setattr(operations, "read_journal", fake_read)

    result = operations.read("arthexis", since="10 minutes ago", until="now", limit=20)

    assert [s.identity for s in captured["sources"]] == [
        "arthexis/portable",
        "arthexis/web",
        "arthexis/worker",
    ]
    assert captured["kwargs"]["since"] == "10 minutes ago"
    assert result == [{
        "timestamp": "2026-09-22T12:00:00+00:00",
        "source": "arthexis/web",
        "level": "INFO",
        "message": "hello",
        "pid": 42,
        "unit": None,
    }]
    assert "SECRET" not in result[0]


def test_zero_source_read_skips_unreadable_backends(catalog_state, monkeypatch):
    captured = {}
    def fake_read(sources, **kwargs):
        captured["sources"] = list(sources)
        return []
    monkeypatch.setattr(operations, "read_journal", fake_read)
    operations.read()
    assert [s.identity for s in captured["sources"]] == [
        "arthexis/portable", "arthexis/web", "arthexis/worker", "gway"
    ]


def test_process_source_uses_journal_identifier_when_journal_available(
    catalog_state,
    monkeypatch,
):
    captured = {}
    def fake_read(sources, **kwargs):
        captured["sources"] = list(sources)
        return []
    monkeypatch.setattr(operations, "read_journal", fake_read)

    operations.read("arthexis/portable")

    assert len(captured["sources"]) == 1
    source = captured["sources"][0]
    assert source.identity == "arthexis/portable"
    assert source.backend == "journal"
    assert source.backend_id == "arthexis/portable"


def test_process_and_gway_sources_use_file_reader_without_journal(
    catalog_state,
    monkeypatch,
    tmp_path,
):
    captured = {}
    monkeypatch.setattr(operations, "_journal_available", lambda: False)
    monkeypatch.setattr(
        operations,
        "_file_paths",
        lambda sources: [tmp_path / "gway.log"],
    )
    def fake_file(sources, **kwargs):
        captured["sources"] = list(sources)
        captured["kwargs"] = kwargs
        return [record("arthexis/portable")]
    monkeypatch.setattr(operations, "read_file_logs", fake_file)

    result = operations.read("arthexis/portable", limit=4)

    assert [source.identity for source in captured["sources"]] == [
        "arthexis/portable"
    ]
    assert captured["kwargs"]["limit"] == 4
    assert result[0]["source"] == "arthexis/portable"


def test_tail_requests_reverse_and_default_limit(catalog_state, monkeypatch):
    captured = {}
    def fake_read(sources, **kwargs):
        captured.update(kwargs)
        return []
    monkeypatch.setattr(operations, "read_journal", fake_read)
    operations.tail("gway")
    assert captured["reverse"] is True
    assert captured["limit"] == 100


def test_search_pushes_pattern_to_backend(catalog_state, monkeypatch):
    captured = {}
    def fake_read(sources, **kwargs):
        captured.update(kwargs)
        return []
    monkeypatch.setattr(operations, "read_journal", fake_read)
    operations.search("timeout.*worker", "gway", limit=5)
    assert captured["grep"] == "timeout.*worker"
    assert captured["limit"] == 5


def test_lazy_recipe_source_works_through_public_operations(catalog_state, monkeypatch):
    captured = {}
    def fake_read(sources, **kwargs):
        captured["sources"] = list(sources)
        return []
    monkeypatch.setattr(operations, "read_journal", fake_read)
    operations.read("recipe/deploy")
    assert [s.identity for s in captured["sources"]] == ["recipe/deploy"]


def test_mixed_reader_results_are_globally_sorted_and_limited(
    catalog_state,
    monkeypatch,
):
    monkeypatch.setattr(operations, "_journal_available", lambda: False)
    monkeypatch.setattr(operations, "_file_paths", lambda sources: [])
    monkeypatch.setattr(
        operations,
        "read_file_logs",
        lambda sources, **kwargs: [
            LogRecord(
                timestamp=datetime(2026, 9, 22, 13, 0, tzinfo=timezone.utc),
                source="gway",
                message="newer",
            ),
            LogRecord(
                timestamp=datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
                source="arthexis/portable",
                message="older",
            ),
        ],
    )

    result = operations.tail("gway", "arthexis/portable", limit=1)

    assert [item["message"] for item in result] == ["newer"]
