import json
import math

import pytest

from gway.reload import (
    CHECKPOINT_VERSION,
    CheckpointState,
    CheckpointVersionError,
    ReloadCheckpoint,
    ReloadError,
    ReloadMode,
    ReloadStore,
)


def test_checkpoint_round_trips_portable_execution_and_journal_state(tmp_path):
    checkpoint = ReloadCheckpoint.create(
        mode=ReloadMode.FRESH,
        when="changed",
        timeout=30,
        source_identity="sha:old",
        target_identity="sha:new",
        recipe_stack=("/recipes/deploy.rx",),
        frames=({"recipe": "/recipes/deploy.rx", "statement": 3},),
        context={"site": "MTY", "enabled": True},
        result={"status": "ready"},
        flags={"verbose": False},
        journal_session_id="session-1",
        open_journals=("deploy",),
    )
    store = ReloadStore(tmp_path / "reload")

    path = store.save(checkpoint)
    loaded = store.load(checkpoint.checkpoint_id)

    assert loaded == checkpoint
    assert path.parent == store.active
    assert path.stat().st_mode & 0o777 == 0o600
    assert loaded.open_journals == ("deploy",)
    assert loaded.journal_session_id == "session-1"


def test_checkpoint_rejects_unsupported_or_nonfinite_transfer_values():
    with pytest.raises(TypeError, match="unsupported reload value"):
        ReloadCheckpoint.create(context={"bad": object()})

    with pytest.raises(TypeError, match="non-finite"):
        ReloadCheckpoint.create(result=math.inf)

    with pytest.raises(TypeError, match="mapping keys must be strings"):
        ReloadCheckpoint.create(context={1: "bad"})


def test_checkpoint_rejects_unknown_schema_version():
    checkpoint = ReloadCheckpoint.create()
    payload = checkpoint.as_dict()
    payload["version"] = CHECKPOINT_VERSION + 1

    with pytest.raises(CheckpointVersionError):
        ReloadCheckpoint.from_dict(payload)


@pytest.mark.parametrize("timeout", [0, -1, math.inf, math.nan])
def test_checkpoint_requires_positive_finite_timeout(timeout):
    with pytest.raises(ValueError, match="finite positive"):
        ReloadCheckpoint.create(timeout=timeout)


def test_when_initially_accepts_only_changed():
    assert ReloadCheckpoint.create(when="changed").when == "changed"

    with pytest.raises(ValueError, match="reload when"):
        ReloadCheckpoint.create(when="always")


def test_checkpoint_lifecycle_is_monotonic():
    prepared = ReloadCheckpoint.create()
    handoff = prepared.transition(CheckpointState.HANDOFF)
    adopted = handoff.transition(CheckpointState.ADOPTED)

    assert handoff.state is CheckpointState.HANDOFF
    assert adopted.state is CheckpointState.ADOPTED

    with pytest.raises(ReloadError, match="Invalid reload checkpoint transition"):
        prepared.transition(CheckpointState.ADOPTED)

    with pytest.raises(ReloadError, match="Invalid reload checkpoint transition"):
        adopted.transition(CheckpointState.HANDOFF)


def test_success_history_is_inert_and_active_checkpoint_is_removed(tmp_path):
    store = ReloadStore(tmp_path / "reload")
    checkpoint = ReloadCheckpoint.create(
        context={"secret_like_value": "must-not-enter-history"},
        result={"token": "also-private"},
        recipe_stack=("deploy.rx",),
        open_journals=("deploy",),
    )
    store.save(checkpoint)

    store.complete(checkpoint)

    assert not store.path(checkpoint.checkpoint_id).exists()
    line = json.loads(store.history.read_text(encoding="utf-8"))
    assert line["checkpoint_id"] == checkpoint.checkpoint_id
    assert line["outcome"] == "completed"
    assert line["recipe_depth"] == 1
    assert line["open_journals"] == ["deploy"]
    assert "context" not in line
    assert "result" not in line
    assert "secret_like_value" not in store.history.read_text(encoding="utf-8")


def test_failed_checkpoint_is_quarantined_outside_active_namespace(tmp_path):
    store = ReloadStore(tmp_path / "reload")
    checkpoint = ReloadCheckpoint.create(context={"site": "MTY"})
    store.save(checkpoint)

    failed = store.quarantine(checkpoint, RuntimeError("resume failed"))

    assert not store.path(checkpoint.checkpoint_id).exists()
    assert failed == store.failed / f"{checkpoint.checkpoint_id}.json"
    assert failed.is_file()
    assert ReloadCheckpoint.from_dict(
        json.loads(failed.read_text(encoding="utf-8"))
    ) == checkpoint

    receipt = json.loads(store.history.read_text(encoding="utf-8"))
    assert receipt["outcome"] == "failed"
    assert receipt["error"] == "resume failed"
    assert "context" not in receipt


def test_checkpoint_payload_uses_explicit_version_and_mode_values():
    checkpoint = ReloadCheckpoint.create(mode=ReloadMode.RESTART)

    payload = checkpoint.as_dict()

    assert payload["version"] == CHECKPOINT_VERSION
    assert payload["mode"] == "restart"
    assert payload["state"] == "prepared"
