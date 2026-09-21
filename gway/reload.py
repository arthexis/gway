"""Versioned reload checkpoint state and diagnostic persistence."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import json
import math
from pathlib import Path
import uuid

from .install.paths import data_root


CHECKPOINT_VERSION = 1


class ReloadError(RuntimeError):
    """Base error for reload checkpoint lifecycle failures."""


class CheckpointVersionError(ReloadError):
    """Raised when a checkpoint schema cannot be consumed safely."""


class CheckpointState(str, Enum):
    """Lifecycle of one executable reload checkpoint."""

    PREPARED = "prepared"
    HANDOFF = "handoff"
    ADOPTED = "adopted"


class ReloadMode(str, Enum):
    """Public reload continuation modes."""

    CONTINUE = "continue"
    FRESH = "fresh"
    RESTART = "restart"


def _timestamp():
    return datetime.now(timezone.utc).isoformat()


def _json_value(value, *, path="value"):
    """Validate and normalize one portable reload value."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError(f"{path} must not contain non-finite numbers")
        return value
    if isinstance(value, (list, tuple)):
        return [
            _json_value(item, path=f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    if isinstance(value, dict):
        normalized = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"{path} mapping keys must be strings")
            normalized[key] = _json_value(item, path=f"{path}.{key}")
        return normalized
    raise TypeError(
        f"{path} contains unsupported reload value {type(value).__name__}"
    )


@dataclass(frozen=True)
class ReloadCheckpoint:
    """Portable state required to resume one suspended GWAY execution."""

    checkpoint_id: str
    version: int = CHECKPOINT_VERSION
    state: CheckpointState = CheckpointState.PREPARED
    created_at: str = field(default_factory=_timestamp)
    mode: ReloadMode = ReloadMode.CONTINUE
    when: str | None = None
    timeout: float | None = None
    source_identity: str | None = None
    target_identity: str | None = None
    recipe_stack: tuple[str, ...] = ()
    frames: tuple[dict[str, object], ...] = ()
    context: dict[str, object] = field(default_factory=dict)
    result: object = None
    flags: dict[str, object] = field(default_factory=dict)
    journal_session_id: str | None = None
    open_journals: tuple[str, ...] = ()

    @classmethod
    def create(cls, **kwargs):
        """Create a checkpoint with a generated opaque identity."""
        return cls(checkpoint_id=uuid.uuid4().hex, **kwargs).validated()

    def validated(self):
        """Return this checkpoint after validating its portable contract."""
        if self.version != CHECKPOINT_VERSION:
            raise CheckpointVersionError(
                f"Unsupported reload checkpoint version {self.version}; "
                f"expected {CHECKPOINT_VERSION}"
            )
        try:
            CheckpointState(self.state)
        except ValueError as exc:
            raise ReloadError(f"Unknown reload checkpoint state: {self.state}") from exc
        try:
            ReloadMode(self.mode)
        except ValueError as exc:
            raise ReloadError(f"Unknown reload mode: {self.mode}") from exc

        if self.when not in {None, "changed"}:
            raise ValueError("reload when must be 'changed' when provided")
        if self.timeout is not None:
            timeout = float(self.timeout)
            if not math.isfinite(timeout) or timeout <= 0:
                raise ValueError("reload timeout must be a finite positive number")

        _json_value(self.context, path="context")
        _json_value(self.result, path="result")
        _json_value(self.flags, path="flags")
        _json_value(list(self.frames), path="frames")
        return self

    def transition(self, state):
        """Return a checkpoint advanced to one valid lifecycle state."""
        target = CheckpointState(state)
        allowed = {
            CheckpointState.PREPARED: {CheckpointState.HANDOFF},
            CheckpointState.HANDOFF: {CheckpointState.ADOPTED},
            CheckpointState.ADOPTED: set(),
        }
        current = CheckpointState(self.state)
        if target not in allowed[current]:
            raise ReloadError(
                f"Invalid reload checkpoint transition "
                f"{current.value} -> {target.value}"
            )
        return replace(self, state=target)

    def as_dict(self):
        """Return the complete executable checkpoint payload."""
        self.validated()
        return {
            "version": self.version,
            "checkpoint_id": self.checkpoint_id,
            "state": CheckpointState(self.state).value,
            "created_at": self.created_at,
            "mode": ReloadMode(self.mode).value,
            "when": self.when,
            "timeout": self.timeout,
            "source_identity": self.source_identity,
            "target_identity": self.target_identity,
            "recipe_stack": list(self.recipe_stack),
            "frames": _json_value(list(self.frames), path="frames"),
            "context": _json_value(self.context, path="context"),
            "result": _json_value(self.result, path="result"),
            "flags": _json_value(self.flags, path="flags"),
            "journal_session_id": self.journal_session_id,
            "open_journals": list(self.open_journals),
        }

    @classmethod
    def from_dict(cls, payload):
        """Load and validate one serialized checkpoint."""
        value = dict(payload)
        version = int(value.get("version", -1))
        if version != CHECKPOINT_VERSION:
            raise CheckpointVersionError(
                f"Unsupported reload checkpoint version {version}; "
                f"expected {CHECKPOINT_VERSION}"
            )
        return cls(
            checkpoint_id=str(value["checkpoint_id"]),
            version=version,
            state=CheckpointState(str(value["state"])),
            created_at=str(value["created_at"]),
            mode=ReloadMode(str(value.get("mode", ReloadMode.CONTINUE.value))),
            when=value.get("when"),
            timeout=value.get("timeout"),
            source_identity=value.get("source_identity"),
            target_identity=value.get("target_identity"),
            recipe_stack=tuple(str(item) for item in value.get("recipe_stack") or ()),
            frames=tuple(dict(item) for item in value.get("frames") or ()),
            context=dict(value.get("context") or {}),
            result=value.get("result"),
            flags=dict(value.get("flags") or {}),
            journal_session_id=value.get("journal_session_id"),
            open_journals=tuple(
                str(item) for item in value.get("open_journals") or ()
            ),
        ).validated()

    def receipt(self, *, outcome, error=None):
        """Return durable non-executable diagnostic metadata."""
        receipt = {
            "version": self.version,
            "checkpoint_id": self.checkpoint_id,
            "created_at": self.created_at,
            "recorded_at": _timestamp(),
            "state": CheckpointState(self.state).value,
            "mode": ReloadMode(self.mode).value,
            "when": self.when,
            "timeout": self.timeout,
            "source_identity": self.source_identity,
            "target_identity": self.target_identity,
            "recipe_depth": len(self.recipe_stack),
            "open_journals": list(self.open_journals),
            "outcome": str(outcome),
        }
        if error is not None:
            receipt["error"] = str(error)
        return receipt


class ReloadStore:
    """Private active checkpoints plus inert reload diagnostic history."""

    def __init__(self, root=None):
        base = data_root() / "reload" if root is None else Path(root)
        self.root = base.expanduser()
        self.active = self.root / "active"
        self.failed = self.root / "failed"
        self.history = self.root / "history.jsonl"

    @staticmethod
    def _atomic_json(path, payload):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        path.parent.chmod(0o700)
        temporary = path.with_name(f".{path.name}.tmp")
        text = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
        temporary.write_text(text, encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(path)
        path.chmod(0o600)

    def path(self, checkpoint_id):
        return self.active / f"{checkpoint_id}.json"

    def save(self, checkpoint):
        """Atomically persist one active executable checkpoint."""
        checkpoint = checkpoint.validated()
        path = self.path(checkpoint.checkpoint_id)
        self._atomic_json(path, checkpoint.as_dict())
        return path

    def load(self, checkpoint_id):
        """Load one active checkpoint by opaque identity."""
        path = self.path(checkpoint_id)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ReloadCheckpoint.from_dict(payload)

    def _record(self, receipt):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        line = json.dumps(receipt, sort_keys=True, allow_nan=False) + "\n"
        with self.history.open("a", encoding="utf-8") as stream:
            stream.write(line)
        self.history.chmod(0o600)

    def complete(self, checkpoint):
        """Record success and remove executable resume state."""
        path = self.path(checkpoint.checkpoint_id)
        self._record(checkpoint.receipt(outcome="completed"))
        path.unlink(missing_ok=True)

    def quarantine(self, checkpoint, error):
        """Make a failed checkpoint inert while preserving private evidence."""
        source = self.path(checkpoint.checkpoint_id)
        target = self.failed / f"{checkpoint.checkpoint_id}.json"
        self.failed.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.failed.chmod(0o700)
        if source.exists():
            source.replace(target)
            target.chmod(0o600)
        else:
            self._atomic_json(target, checkpoint.as_dict())
        self._record(checkpoint.receipt(outcome="failed", error=error))
        return target
