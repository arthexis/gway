from __future__ import annotations

import json

import pytest

from gway.dispatcher.errors import DispatchError
from gway.event import FileEventBackend, pub, publish
from gway.event_command import run_event
from gway.runtime import GwayRuntime


def test_publish_appends_jsonl_to_file(tmp_path) -> None:
    target = tmp_path / "events.jsonl"
    result = publish("rfid.scanned", path=target, uid="04A1B2C3")

    assert result["type"] == "rfid.scanned"
    assert result["data"] == {"uid": "04A1B2C3"}
    assert result["time"]
    assert json.loads(target.read_text(encoding="utf-8").strip()) == result


def test_pub_is_publish_alias(tmp_path) -> None:
    target = tmp_path / "events.jsonl"
    result = pub("service.failed", path=target, service="arthexis")
    assert result["type"] == "service.failed"


def test_file_backend_uses_xdg_state_home_by_default(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path))
    result = run_event(["pub", "network.connected", "--interface", "wlan0"])
    target = tmp_path / "gway" / "events.jsonl"
    assert target.exists()
    assert json.loads(target.read_text(encoding="utf-8").strip()) == result


def test_publish_and_pub_commands_are_equivalent(tmp_path) -> None:
    target = tmp_path / "events.jsonl"
    first = run_event(["publish", "demo.one", "--path", str(target), "--value", "1"])
    second = run_event(["pub", "demo.two", "--path", str(target), "--value", "2"])

    assert first["data"]["value"] == 1
    assert second["data"]["value"] == 2
    assert len(target.read_text(encoding="utf-8").splitlines()) == 2


def test_backend_is_selectable(tmp_path) -> None:
    target = tmp_path / "events.jsonl"
    result = run_event(
        ["pub", "demo.event", "--backend", "file", "--path", str(target), "--ready"]
    )
    assert result["data"]["ready"] is True


def test_unknown_backend_is_dispatch_error() -> None:
    with pytest.raises(DispatchError, match="unknown event backend"):
        run_event(["pub", "demo.event", "--backend", "missing"])


def test_runtime_exposes_event_as_core_operation(tmp_path) -> None:
    target = tmp_path / "events.jsonl"
    result = GwayRuntime()._run_core(
        ["event", "pub", "demo.event", "--path", str(target), "--message", "hello"]
    )
    assert result["type"] == "demo.event"
    assert result["data"]["message"] == "hello"


def test_file_backend_can_be_constructed_explicitly(tmp_path) -> None:
    target = tmp_path / "events.jsonl"
    backend = FileEventBackend(target)
    assert backend.path == target
