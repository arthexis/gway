import threading
import time
import importlib

import pytest

from gway import gw


@pytest.fixture
def side_module():
    module = importlib.import_module("gway.builtins.side")
    module._reset_side_state_for_tests()
    original_threads = list(gw._async_threads)
    yield module
    new_threads = [t for t in gw._async_threads if t not in original_threads]
    for thread in new_threads:
        thread.join(timeout=1)
    module._reset_side_state_for_tests()
    gw._async_threads.clear()
    gw._async_threads.extend(original_threads)


def test_side_default_queue_serializes_commands(side_module, monkeypatch):
    start_events: list[tuple[list[str], threading.Event]] = []
    release_events: list[threading.Event] = []
    threads_seen: list[threading.Thread] = []

    def fake_process(chunks, **kwargs):
        command = list(chunks[0])
        start_evt = threading.Event()
        release_evt = threading.Event()
        start_events.append((command, start_evt))
        release_events.append(release_evt)
        threads_seen.append(threading.current_thread())
        start_evt.set()
        release_evt.wait(timeout=1)
        return ([], None)

    monkeypatch.setattr("gway.console.process", fake_process)

    result_first = side_module.side("hello-world")
    assert result_first["status"] == "started"
    assert start_events[0][0] == ["hello-world"]
    assert start_events[0][1].wait(timeout=1)

    result_second = side_module.side("hello-world")
    assert result_second["status"] == "queued"
    time.sleep(0.05)
    assert len(start_events) == 1

    release_events[0].set()
    for _ in range(20):
        if len(start_events) >= 2:
            break
        time.sleep(0.05)
    assert len(start_events) == 2
    assert start_events[1][0] == ["hello-world"]
    release_events[1].set()

    for thread in list(threads_seen):
        thread.join(timeout=1)


def test_side_named_queues_and_multiplex(side_module, monkeypatch):
    start_records: list[tuple[list[str], threading.Event]] = []
    release_events: list[threading.Event] = []
    threads_seen: list[threading.Thread] = []

    def fake_process(chunks, **kwargs):
        command = list(chunks[0])
        start_evt = threading.Event()
        release_evt = threading.Event()
        start_records.append((command, start_evt))
        release_events.append(release_evt)
        threads_seen.append(threading.current_thread())
        start_evt.set()
        release_evt.wait(timeout=1)
        return ([], None)

    monkeypatch.setattr("gway.console.process", fake_process)

    ready_alpha = side_module.side("alpha")
    assert ready_alpha["status"] == "ready"

    first = side_module.side("alpha", "beta:", "hello-world", "--id", "A")
    assert first["status"] == "started"
    assert start_records[0][0] == ["hello-world", "--id", "A"]
    assert start_records[0][1].wait(timeout=1)

    second = side_module.side("alpha", "hello-world", "--id", "B")
    third = side_module.side("beta", "hello-world", "--id", "C")
    assert second["status"] == "queued"
    assert third["status"] == "queued"
    time.sleep(0.05)
    assert len(start_records) == 1

    release_events[0].set()
    for _ in range(20):
        if len(start_records) >= 3:
            break
        time.sleep(0.05)
    assert len(start_records) == 3

    seen_ids = {tuple(record[0]) for record in start_records}
    assert ("hello-world", "--id", "A") in seen_ids
    assert ("hello-world", "--id", "B") in seen_ids
    assert ("hello-world", "--id", "C") in seen_ids

    release_events[1].set()
    release_events[2].set()

    for thread in list(threads_seen):
        thread.join(timeout=1)


def test_side_supports_colon_queue_names(side_module, monkeypatch):
    commands_seen: list[list[str]] = []

    def quick_process(chunks, **kwargs):
        commands_seen.append(list(chunks[0]))
        return ([], None)

    monkeypatch.setattr("gway.console.process", quick_process)

    result = side_module.side("watcher:", "hello-world")
    assert result["status"] == "started"

    for _ in range(20):
        if commands_seen:
            break
        time.sleep(0.05)
    assert commands_seen[0] == ["hello-world"]
    assert "watcher" in side_module._SIDE_QUEUES


def test_side_when_condition_false_skips_queue_initialization(side_module, monkeypatch):
    logs: list[str] = []

    def capture_debug(message, *args, **kwargs):
        logs.append(message)

    monkeypatch.setattr(gw, "debug", capture_debug)

    def fail_process(*args, **kwargs):
        raise AssertionError("process should not be called when --when is false")

    monkeypatch.setattr("gway.console.process", fail_process)

    result = side_module.side("alpha", when="false")

    assert result["status"] == "skipped"
    assert result["queues"] == ["alpha"]
    assert result["command"] is None
    assert side_module._SIDE_QUEUES == {}
    assert any("skipped" in message for message in logs)


def test_side_when_condition_false_skips_commands(side_module, monkeypatch):
    logs: list[str] = []

    def capture_debug(message, *args, **kwargs):
        logs.append(message)

    monkeypatch.setattr(gw, "debug", capture_debug)

    def fail_process(*args, **kwargs):
        raise AssertionError("process should not be called when --when is false")

    monkeypatch.setattr("gway.console.process", fail_process)

    result = side_module.side("hello-world", when=False)

    assert result["status"] == "skipped"
    assert result["queues"] == [side_module._DEFAULT_QUEUE]
    assert result["command"] == "hello-world"
    assert side_module._SIDE_QUEUES == {}
    assert any("hello-world" in message for message in logs)
