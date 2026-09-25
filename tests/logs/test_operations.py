from datetime import datetime, timezone

import pytest

from gway.install.service import ServiceInstallRecord, ServiceInstallState
from gway.logs import LogRecord
from gway.logs import operations


@pytest.fixture
def catalog_state(tmp_path, monkeypatch):
    state = ServiceInstallState(tmp_path)
    state.put(
        "arthexis",
        [
            ServiceInstallRecord(
                project="arthexis",
                service="web",
                backend_id="arthexis-web.service",
                backend="systemd",
                system=False,
            ),
            ServiceInstallRecord(
                project="arthexis",
                service="worker",
                backend_id="arthexis-worker.service",
                backend="systemd",
                system=False,
            ),
            ServiceInstallRecord(
                project="arthexis",
                service="portable",
                backend_id="portable",
                backend="process",
                system=False,
            ),
        ],
    )
    monkeypatch.setattr(operations, "_install_state", lambda: state)
    monkeypatch.setattr(operations, "_journal_available", lambda: True)
    return state


def _record(source="gway", *, hour=12, message="hello"):
    return LogRecord(
        timestamp=datetime(2026, 9, 22, hour, 0, tzinfo=timezone.utc),
        source=source,
        message=message,
        level="INFO",
        pid=42,
        unit=None,
        metadata={"SECRET": "hidden"},
    )


def test_sources_returns_serializable_catalog(catalog_state):
    result = operations.sources()

    assert [item["identity"] for item in result] == [
        "gway",
        "arthexis",
        "arthexis/portable",
        "arthexis/web",
        "arthexis/worker",
    ]


def test_read_expands_project_to_readable_members(catalog_state, monkeypatch):
    captured = {}

    def fake_read(sources, **kwargs):
        captured["sources"] = list(sources)
        captured["kwargs"] = kwargs
        return [_record("arthexis/web")]

    monkeypatch.setattr(operations, "read_journal", fake_read)

    result = operations.read(
        "arthexis",
        since="10 minutes ago",
        until="now",
        limit=20,
    )

    assert [source.identity for source in captured["sources"]] == [
        "arthexis/portable",
        "arthexis/web",
        "arthexis/worker",
    ]
    assert captured["kwargs"] == {
        "since": "10 minutes ago",
        "until": "now",
        "limit": 20,
        "grep": None,
        "reverse": False,
    }
    assert result == [
        {
            "timestamp": "2026-09-22T12:00:00+00:00",
            "source": "arthexis/web",
            "level": "INFO",
            "message": "hello",
            "pid": 42,
            "unit": None,
        }
    ]
    assert "SECRET" not in result[0]


def test_zero_source_read_returns_catalog_without_reading(catalog_state, monkeypatch):
    monkeypatch.setattr(
        operations,
        "read_journal",
        lambda *args, **kwargs: pytest.fail("journal should not be read"),
    )

    result = operations.read()

    assert [item["identity"] for item in result] == [
        "gway",
        "arthexis",
        "arthexis/portable",
        "arthexis/web",
        "arthexis/worker",
    ]


def test_all_explicitly_selects_all_managed_sources(catalog_state, monkeypatch):
    captured = {}

    def fake_read(sources, **kwargs):
        captured["sources"] = list(sources)
        captured["kwargs"] = kwargs
        return []

    monkeypatch.setattr(operations, "read_journal", fake_read)

    operations.read(all=True)

    assert [source.identity for source in captured["sources"]] == [
        "arthexis/portable",
        "arthexis/web",
        "arthexis/worker",
        "gway",
    ]
    assert captured["kwargs"]["limit"] == 100


def test_explicit_source_cannot_be_combined_with_all(catalog_state):
    with pytest.raises(ValueError, match="cannot be combined with --all"):
        operations.read("gway", all=True)


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


def test_process_source_uses_file_reader_without_journal(
    catalog_state,
    monkeypatch,
    tmp_path,
):
    captured = {}
    log_path = tmp_path / "gway.log"
    monkeypatch.setattr(operations, "_journal_available", lambda: False)
    monkeypatch.setattr(operations, "_file_paths", lambda sources: [log_path])

    def fake_file(sources, **kwargs):
        captured["sources"] = list(sources)
        captured["kwargs"] = kwargs
        return [_record("arthexis/portable")]

    monkeypatch.setattr(operations, "read_file_logs", fake_file)

    result = operations.read("arthexis/portable", limit=4)

    assert [source.identity for source in captured["sources"]] == [
        "arthexis/portable"
    ]
    assert captured["kwargs"]["paths"] == [log_path]
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


def test_read_and_search_default_to_bounded_queries(catalog_state, monkeypatch):
    captured = []

    def fake_read(sources, **kwargs):
        captured.append(kwargs)
        return []

    monkeypatch.setattr(operations, "read_journal", fake_read)

    operations.read("gway")
    operations.search("timeout", "gway")

    assert [item["limit"] for item in captured] == [100, 100]


def test_zero_source_tail_and_search_return_catalog(catalog_state, monkeypatch):
    monkeypatch.setattr(
        operations,
        "read_journal",
        lambda *args, **kwargs: pytest.fail("journal should not be read"),
    )

    tail_result = operations.tail()
    search_result = operations.search("timeout")

    expected = [
        "gway",
        "arthexis",
        "arthexis/portable",
        "arthexis/web",
        "arthexis/worker",
    ]
    assert [item["identity"] for item in tail_result] == expected
    assert [item["identity"] for item in search_result] == expected


def test_lazy_recipe_source_works_through_public_operations(
    catalog_state,
    monkeypatch,
):
    captured = {}

    def fake_read(sources, **kwargs):
        captured["sources"] = list(sources)
        return []

    monkeypatch.setattr(operations, "read_journal", fake_read)

    operations.read("recipe/deploy")

    assert [source.identity for source in captured["sources"]] == [
        "recipe/deploy"
    ]


def test_reader_results_are_globally_sorted_and_limited(
    catalog_state,
    monkeypatch,
):
    monkeypatch.setattr(operations, "_journal_available", lambda: False)
    monkeypatch.setattr(operations, "_file_paths", lambda sources: [])
    monkeypatch.setattr(
        operations,
        "read_file_logs",
        lambda sources, **kwargs: [
            _record("gway", hour=13, message="newer"),
            _record("arthexis/portable", hour=12, message="older"),
        ],
    )

    result = operations.tail("gway", "arthexis/portable", limit=1)

    assert [item["message"] for item in result] == ["newer"]
