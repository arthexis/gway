"""Versioned reload checkpoint state and diagnostic persistence."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from enum import Enum
import json
import math
from pathlib import Path
import subprocess
import sys
import time
import uuid

from .install.paths import data_root


CHECKPOINT_VERSION = 1
_INSTALLATION_TAG = "$gway.installation"


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
    from .install.model import Installation

    if isinstance(value, Installation):
        return {
            _INSTALLATION_TAG: {
                "name": value.name,
                "source": value.source,
                "install_path": str(value.install_path),
                "scope": value.scope,
                "requested_ref": value.requested_ref,
                "resolved_revision": value.resolved_revision,
                "fingerprint": value.fingerprint,
                "installed_at": value.installed_at,
            }
        }
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, Path):
        return str(value)
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


def _restore_json_value(value):
    """Restore explicitly supported typed values from checkpoint JSON."""
    if isinstance(value, list):
        return [_restore_json_value(item) for item in value]
    if isinstance(value, dict):
        if set(value) == {_INSTALLATION_TAG}:
            from .install.model import Installation

            data = dict(value[_INSTALLATION_TAG])
            return Installation(
                name=str(data["name"]),
                source=str(data["source"]),
                install_path=Path(str(data["install_path"])),
                scope=str(data.get("scope", "user")),
                requested_ref=data.get("requested_ref"),
                resolved_revision=data.get("resolved_revision"),
                fingerprint=data.get("fingerprint"),
                installed_at=data.get("installed_at"),
            )
        return {key: _restore_json_value(item) for key, item in value.items()}
    return value


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
    result_history: tuple[object, ...] = ()
    result_subjects: dict[str, object] = field(default_factory=dict)
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
        _json_value(list(self.result_history), path="result_history")
        _json_value(self.result_subjects, path="result_subjects")
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
            "result_history": _json_value(
                list(self.result_history),
                path="result_history",
            ),
            "result_subjects": _json_value(
                self.result_subjects,
                path="result_subjects",
            ),
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
            frames=tuple(
                dict(_restore_json_value(item))
                for item in value.get("frames") or ()
            ),
            context=dict(_restore_json_value(value.get("context") or {})),
            result=_restore_json_value(value.get("result")),
            result_history=tuple(
                _restore_json_value(value.get("result_history") or ())
            ),
            result_subjects=dict(
                _restore_json_value(value.get("result_subjects") or {})
            ),
            flags=dict(_restore_json_value(value.get("flags") or {})),
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

    def adopted_path(self, checkpoint_id):
        return self.active / f"{checkpoint_id}.adopted.json"

    def acknowledgement_path(self, checkpoint_id):
        return self.root / "ack" / f"{checkpoint_id}.json"

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

    def claim(self, checkpoint_id):
        """Atomically claim one HANDOFF checkpoint without transferring ownership."""
        source = self.path(checkpoint_id)
        claimed = self.adopted_path(checkpoint_id)
        self.active.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            source.replace(claimed)
        except FileNotFoundError:
            if claimed.exists():
                raise ReloadError(
                    f"Reload checkpoint {checkpoint_id!r} is already claimed"
                )
            raise

        try:
            payload = json.loads(claimed.read_text(encoding="utf-8"))
            checkpoint = ReloadCheckpoint.from_dict(payload)
            if checkpoint.state is not CheckpointState.HANDOFF:
                raise ReloadError(
                    f"Reload checkpoint {checkpoint_id!r} is "
                    f"{checkpoint.state.value}, not handoff"
                )
            return checkpoint
        except Exception:
            if claimed.exists() and not source.exists():
                claimed.replace(source)
            raise

    def acknowledge(self, checkpoint):
        """Transfer ownership after the successor has restored runtime state."""
        if checkpoint.state is not CheckpointState.HANDOFF:
            raise ReloadError(
                f"Reload checkpoint {checkpoint.checkpoint_id!r} is "
                f"{checkpoint.state.value}, not handoff"
            )
        adopted = checkpoint.transition(CheckpointState.ADOPTED)
        claimed = self.adopted_path(checkpoint.checkpoint_id)
        if not claimed.exists():
            raise ReloadError(
                f"Reload checkpoint {checkpoint.checkpoint_id!r} is not claimed"
            )
        self._atomic_json(claimed, adopted.as_dict())
        ack = self.acknowledgement_path(checkpoint.checkpoint_id)
        self._atomic_json(
            ack,
            {
                "checkpoint_id": checkpoint.checkpoint_id,
                "state": CheckpointState.ADOPTED.value,
                "recorded_at": _timestamp(),
            },
        )
        return adopted

    def adopt(self, checkpoint_id):
        """Claim and immediately acknowledge a HANDOFF checkpoint."""
        checkpoint = self.claim(checkpoint_id)
        return self.acknowledge(checkpoint)

    def acknowledged(self, checkpoint_id):
        """Return whether the successor durably acknowledged ownership."""
        return self.acknowledgement_path(checkpoint_id).is_file()

    def clear_acknowledgement(self, checkpoint_id):
        """Remove one non-executable ownership acknowledgement."""
        self.acknowledgement_path(checkpoint_id).unlink(missing_ok=True)

    def _record(self, receipt):
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.root.chmod(0o700)
        line = json.dumps(receipt, sort_keys=True, allow_nan=False) + "\n"
        with self.history.open("a", encoding="utf-8") as stream:
            stream.write(line)
        self.history.chmod(0o600)

    def complete(self, checkpoint):
        """Record success and remove executable resume state."""
        self._record(checkpoint.receipt(outcome="completed"))
        self.path(checkpoint.checkpoint_id).unlink(missing_ok=True)
        self.adopted_path(checkpoint.checkpoint_id).unlink(missing_ok=True)

    def quarantine(self, checkpoint, error):
        """Make a failed checkpoint inert while preserving private evidence."""
        source = self.path(checkpoint.checkpoint_id)
        adopted = self.adopted_path(checkpoint.checkpoint_id)
        target = self.failed / f"{checkpoint.checkpoint_id}.json"
        self.failed.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.failed.chmod(0o700)
        if source.exists():
            source.replace(target)
            target.chmod(0o600)
        elif adopted.exists():
            adopted.replace(target)
            target.chmod(0o600)
        else:
            self._atomic_json(target, checkpoint.as_dict())
        self._record(checkpoint.receipt(outcome="failed", error=error))
        return target


class ReloadTransferred(BaseException):
    """Internal control signal indicating execution moved to a successor."""

    def __init__(self, process, checkpoint, journal_root):
        self.process = process
        self.checkpoint = checkpoint
        self.checkpoint_id = str(checkpoint.checkpoint_id)
        self.journal_root = Path(journal_root)
        super().__init__(self.checkpoint_id)


class ReloadSuccessorError(ReloadError):
    """Raised when an adopted reload successor exits abnormally."""

    def __init__(self, checkpoint, returncode):
        self.checkpoint = checkpoint
        self.returncode = int(returncode)
        super().__init__(
            f"Reload successor exited after adoption with code {self.returncode}"
        )


class ReloadHandoffError(ReloadError):
    """Raised when a successor cannot safely adopt a reload checkpoint."""

    def __init__(self, checkpoint, message, *, timeout=None, returncode=None):
        self.checkpoint = checkpoint
        self.timeout = timeout
        self.returncode = returncode
        super().__init__(message)


def recover_adopted_journals(checkpoint, journal_root):
    """Roll back only journals still durably open after successor failure."""
    if (
        ReloadMode(checkpoint.mode) is ReloadMode.RESTART
        or checkpoint.journal_session_id is None
    ):
        return (), ()

    from .journal import JournalManager

    manager = JournalManager(
        journal_root,
        session_id=checkpoint.journal_session_id,
    )
    recovered = []
    errors = []
    for name in reversed(manager.open_names()):
        try:
            manager.rollback(name)
        except Exception as exception:
            errors.append(exception)
        else:
            recovered.append(name)
    return tuple(recovered), tuple(errors)


def supervise_successor(process, checkpoint, journal_root):
    """Wait for one adopted successor and recover open journals on hard failure."""
    returncode = process.wait()
    if returncode == 0:
        return 0

    error = ReloadSuccessorError(checkpoint, returncode)
    recovered = ()
    failures = ()
    if ReloadMode(checkpoint.mode) is not ReloadMode.RESTART:
        recovered, failures = recover_adopted_journals(checkpoint, journal_root)
    if failures:
        from .journal import RollbackRecoveryError, attach_rollback_error

        rollback_error = (
            failures[0]
            if len(failures) == 1
            else RollbackRecoveryError(failures)
        )
        attach_rollback_error(error, rollback_error)
    error.recovered_journals = tuple(recovered)
    raise error


def _stop_successor(process):
    """Best-effort termination of an unacknowledged successor."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=1)


def handoff(
    runtime,
    checkpoint,
    command,
    *,
    store=None,
    popen=subprocess.Popen,
    poll_interval=0.01,
):
    """Start a successor and retain rollback ownership until it acknowledges."""
    store = ReloadStore() if store is None else store
    if checkpoint.state is not CheckpointState.PREPARED:
        raise ReloadError("reload handoff requires a prepared checkpoint")

    handoff_checkpoint = checkpoint.transition(CheckpointState.HANDOFF)
    store.save(handoff_checkpoint)
    runtime.suspend_execution(handoff_checkpoint)

    argv = [*map(str, command), "--resume", handoff_checkpoint.checkpoint_id]
    process = None
    try:
        process = popen(argv)
    except BaseException as exception:
        store.quarantine(handoff_checkpoint, exception)
        raise ReloadHandoffError(
            handoff_checkpoint,
            f"Unable to start reload successor: {exception}",
        ) from exception

    timeout = handoff_checkpoint.timeout or 30.0
    deadline = time.monotonic() + timeout
    try:
        while True:
            if store.acknowledged(handoff_checkpoint.checkpoint_id):
                store.clear_acknowledgement(handoff_checkpoint.checkpoint_id)
                return process, handoff_checkpoint

            returncode = process.poll()
            if returncode is not None:
                error = ReloadHandoffError(
                    handoff_checkpoint,
                    f"Reload successor exited before adoption with code {returncode}",
                    returncode=returncode,
                )
                store.quarantine(handoff_checkpoint, error)
                raise error

            if time.monotonic() >= deadline:
                _stop_successor(process)
                error = ReloadHandoffError(
                    handoff_checkpoint,
                    f"Reload successor did not adopt checkpoint within {timeout:g}s",
                    timeout=timeout,
                )
                store.quarantine(handoff_checkpoint, error)
                raise error

            time.sleep(poll_interval)
    except BaseException:
        if process is not None and not store.acknowledged(
            handoff_checkpoint.checkpoint_id
        ):
            _stop_successor(process)
        raise


def capture_reload_checkpoint(
    runtime,
    *,
    mode=ReloadMode.CONTINUE,
    when=None,
    timeout=None,
    source_identity=None,
    target_identity=None,
):
    """Snapshot the live recipe continuation into one portable checkpoint."""
    frames = list(getattr(runtime, "_recipe_frames", ()) or ())
    if not frames:
        raise ReloadError("reload requires an active recipe execution")

    serialized_frames = []
    for frame in frames:
        serialized_frames.append(
            {
                "recipe": str(frame.path),
                "pipeline": serialize_tokens(frame.pipeline_remaining),
                "statements": [
                    serialize_tokens(statement)
                    for statement in frame.remaining_statements
                ],
            }
        )

    flags = {
        "debug": runtime.debug_enabled,
        "verbose": runtime.verbose,
        "silent": runtime.silent,
        "interactive": runtime.interactive_enabled,
        "timed": runtime.timed_enabled,
    }
    selected_mode = ReloadMode(mode)
    if selected_mode is ReloadMode.FRESH:
        context = {}
        subjects = {}
        history = ()
    else:
        context = dict(runtime.context)
        subjects = dict(runtime.results.maps[0])
        history = tuple(runtime.results.history)

    return ReloadCheckpoint.create(
        mode=selected_mode,
        when=when,
        timeout=timeout,
        source_identity=source_identity,
        target_identity=target_identity,
        recipe_stack=tuple(str(frame.path) for frame in frames),
        frames=tuple(serialized_frames),
        context=context,
        result=runtime.results.last,
        result_history=history,
        result_subjects=subjects,
        flags=flags,
        journal_session_id=runtime.journal.session_id,
        open_journals=runtime.journal.open_names(),
    )


def default_resume_command():
    """Return the managed GWAY launcher when available, else this interpreter."""
    from .install.paths import install_paths

    launcher = install_paths().bin / "gway"
    if launcher.is_file():
        return [str(launcher)]
    return [sys.executable, "-m", "gway"]


def _restart_plan(runtime):
    """Capture top-level recipe invocation needed for a clean restart."""
    frames = list(getattr(runtime, "_recipe_frames", ()) or ())
    if not frames:
        raise ReloadError("reload requires an active recipe execution")
    top = frames[0]
    return {
        "recipe": str(top.path),
        "context": dict(top.invocation_context),
        "section": top.section,
    }


def _rollback_for_restart(runtime):
    """Roll back every open journal newest-first before restart handoff."""
    for name in reversed(runtime.journal.open_names()):
        runtime.journal.rollback(name)
    if runtime.journal.open_names():
        raise ReloadError("restart rollback did not close every rollback journal")


def _restart_checkpoint(
    runtime,
    plan,
    *,
    timeout,
    when,
    source_identity,
    target_identity,
):
    """Build a restart checkpoint only after old transactional state is clean."""
    flags = {
        "debug": runtime.debug_enabled,
        "verbose": runtime.verbose,
        "silent": runtime.silent,
        "interactive": runtime.interactive_enabled,
        "timed": runtime.timed_enabled,
    }
    return ReloadCheckpoint.create(
        mode=ReloadMode.RESTART,
        when=when,
        timeout=timeout,
        source_identity=source_identity,
        target_identity=target_identity,
        recipe_stack=(plan["recipe"],),
        frames=(
            {
                "recipe": plan["recipe"],
                "context": _json_value(plan["context"], path="restart_context"),
                "section": plan["section"],
            },
        ),
        context={},
        result=None,
        result_history=(),
        result_subjects={},
        flags=flags,
        journal_session_id=None,
        open_journals=(),
    )


def perform_reload(
    runtime,
    *,
    timeout=30.0,
    when=None,
    store=None,
    command=None,
    installed_identity=None,
    fresh=False,
    restart=False,
):
    """Conditionally capture, hand off, and stop after successor adoption."""
    if when not in {None, "changed"}:
        raise ReloadError(f"Unknown reload condition: {when!r}")
    if fresh and restart:
        raise ReloadError("reload --fresh and --restart are mutually exclusive")

    source = getattr(runtime, "gway_identity", None)
    target = installed_identity
    if when == "changed":
        if source is None:
            raise ReloadError(
                "Cannot evaluate reload --when changed: "
                "running GWAY identity is unavailable"
            )
        if target is None:
            from .install.identity import managed_gway_identity

            target = managed_gway_identity()
        if target is None:
            raise ReloadError(
                "Cannot evaluate reload --when changed: "
                "installed GWAY identity is unavailable"
            )
        try:
            unchanged = source.same_runtime(target)
        except ValueError as exception:
            raise ReloadError(
                "Cannot evaluate reload --when changed: "
                f"{exception}"
            ) from exception
        if unchanged:
            from .publication import SKIP_PUBLICATION

            return SKIP_PUBLICATION

    source_diagnostic = source.diagnostic() if source is not None else None
    target_diagnostic = target.diagnostic() if target is not None else None

    if restart:
        plan = _restart_plan(runtime)
        _rollback_for_restart(runtime)
        checkpoint = _restart_checkpoint(
            runtime,
            plan,
            timeout=timeout,
            when=when,
            source_identity=source_diagnostic,
            target_identity=target_diagnostic,
        )
    else:
        checkpoint = capture_reload_checkpoint(
            runtime,
            mode=ReloadMode.FRESH if fresh else ReloadMode.CONTINUE,
            timeout=timeout,
            when=when,
            source_identity=source_diagnostic,
            target_identity=target_diagnostic,
        )
    selected = default_resume_command() if command is None else list(command)
    process, handoff_checkpoint = handoff(
        runtime,
        checkpoint,
        selected,
        store=store,
    )
    raise ReloadTransferred(
        process,
        handoff_checkpoint,
        runtime.journal.root,
    )


def _restore_runtime(checkpoint):
    """Construct a fresh Gateway and restore portable semantic/runtime state."""
    from .gateway import Gateway
    from .journal import JournalManager

    flags = dict(checkpoint.flags)
    allowed_flags = {
        "debug": bool(flags.get("debug", False)),
        "verbose": bool(flags.get("verbose", False)),
        "silent": bool(flags.get("silent", False)),
        "interactive": bool(flags.get("interactive", False)),
        "timed": bool(flags.get("timed", False)),
    }
    runtime = Gateway(**allowed_flags)
    runtime.context.clear()
    runtime.context.update(checkpoint.context)
    runtime.context["verbose"] = runtime.verbose
    runtime.context["silent"] = runtime.silent

    runtime.results.clear()
    runtime.results.history.extend(checkpoint.result_history)
    runtime.results.maps[0].update(checkpoint.result_subjects)

    if checkpoint.journal_session_id is not None:
        runtime.journal = JournalManager(
            runtime.journal.root,
            session_id=checkpoint.journal_session_id,
        )
        actual = runtime.journal.open_names()
        if actual != tuple(checkpoint.open_journals):
            raise ReloadError(
                "Reload checkpoint journals do not match persisted rollback session: "
                f"expected {tuple(checkpoint.open_journals)!r}, got {actual!r}"
            )
    elif checkpoint.open_journals:
        raise ReloadError("Reload checkpoint has journals without a journal session")
    return runtime


def serialize_tokens(tokens):
    """Serialize lexical tokens without losing quote provenance."""
    from .tokens import token_value

    return [
        {
            "value": token_value(token),
            "quote": getattr(token, "quote", None),
        }
        for token in tokens
    ]


def _frame_tokens(value):
    """Restore one serialized token sequence with quote provenance."""
    from .tokens import Token

    tokens = []
    for item in value or ():
        if isinstance(item, str):
            tokens.append(Token(item))
            continue
        data = dict(item)
        tokens.append(Token(str(data["value"]), data.get("quote")))
    return tokens


def resume_frames(runtime, checkpoint):
    """Resume or restart recipe execution from one adopted checkpoint."""
    from .dispatch import dispatch_pipeline, dispatch_program
    from .recipes import execute_recipe, ingest_companion
    from pathlib import Path

    frames = [dict(frame) for frame in checkpoint.frames]
    if not frames:
        return checkpoint.result

    if checkpoint.mode is ReloadMode.RESTART:
        frame = frames[0]
        _, value = execute_recipe(
            runtime,
            frame["recipe"],
            context=dict(frame.get("context") or {}),
            section=frame.get("section"),
        )
        return value

    recipe_paths = [Path(str(frame["recipe"])).expanduser().resolve() for frame in frames]
    runtime._recipe_stack = []
    for path in recipe_paths:
        ingest_companion(runtime, path)

    current = checkpoint.result
    for depth in range(len(frames) - 1, -1, -1):
        frame = frames[depth]
        path = recipe_paths[depth]
        runtime._recipe_stack = recipe_paths[: depth + 1]

        pipeline_tokens = _frame_tokens(frame.get("pipeline"))
        if pipeline_tokens:
            _, current = dispatch_pipeline(
                runtime,
                pipeline_tokens,
                pipeline=current,
            )

        remaining = [
            _frame_tokens(statement)
            for statement in frame.get("statements") or ()
        ]
        if remaining:
            _, current = dispatch_program(runtime, remaining)

    runtime._recipe_stack = []
    return current


def resume(checkpoint_id, *, store=None):
    """Adopt one suspended reload checkpoint and continue its recipe frames."""
    store = ReloadStore() if store is None else store
    checkpoint = store.claim(checkpoint_id)
    runtime = None
    try:
        runtime = _restore_runtime(checkpoint)
        checkpoint = store.acknowledge(checkpoint)
        with runtime.execution_scope():
            value = resume_frames(runtime, checkpoint)
        store.complete(checkpoint)
        return value
    except BaseException as exception:
        store.quarantine(checkpoint, exception)
        raise
