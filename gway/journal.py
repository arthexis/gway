"""Invocation-scoped rollback journal state and persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
import re
import shutil
import uuid

from .log import debug, error, info


_JOURNAL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_ROLLBACK_ERROR_ATTR = "_gway_rollback_error"


class JournalError(RuntimeError):
    """Base error for rollback journal lifecycle violations."""


class UncommittedJournalError(JournalError):
    """Raised when an outer execution ends with unresolved rollback journals."""

    def __init__(self, journals, *, rollback_errors=()):
        self.journals = tuple(str(name) for name in journals)
        self.rollback_errors = tuple(rollback_errors)
        if not self.journals:
            raise ValueError("UncommittedJournalError requires at least one journal")
        names = ", ".join(repr(name) for name in self.journals)
        recovery = (
            "automatic rollback was incomplete"
            if self.rollback_errors
            else "changes were rolled back automatically"
        )
        super().__init__(
            f"Execution ended with uncommitted rollback journal"
            f"{'s' if len(self.journals) != 1 else ''}: {names}; {recovery}"
        )


@dataclass(frozen=True)
class RollbackFailure:
    """One failed journal entry restoration with its original exception."""

    journal: str
    sequence: int
    operation: str | None
    error: BaseException

    def __str__(self) -> str:
        operation = self.operation or "unknown"
        return f"entry {self.sequence} {operation}: {self.error}"


class RollbackError(JournalError):
    """Aggregate error describing an incomplete rollback attempt."""

    def __init__(
        self,
        journal: str,
        failures: list[RollbackFailure] | tuple[RollbackFailure, ...],
        *,
        attempted: int | None = None,
    ) -> None:
        self.journal = str(journal)
        self.failures = tuple(failures)
        self.attempted = attempted
        if not self.failures:
            raise ValueError("RollbackError requires at least one failure")
        super().__init__(self._message())

    def _message(self) -> str:
        failed = len(self.failures)
        if self.attempted is None:
            summary = (
                f"Rollback journal {self.journal!r} incomplete: "
                f"{failed} entr{'y' if failed == 1 else 'ies'} failed"
            )
        else:
            summary = (
                f"Rollback journal {self.journal!r} incomplete: "
                f"{failed} of {self.attempted} entries failed"
            )
        details = "\n".join(f"  {failure}" for failure in self.failures)
        return f"{summary}\n{details}"


class RollbackRecoveryError(JournalError):
    """Aggregate rollback failures spanning multiple journals."""

    def __init__(self, errors):
        self.errors = tuple(errors)
        if not self.errors:
            raise ValueError("RollbackRecoveryError requires at least one error")
        self.journals = tuple(error.journal for error in self.errors)
        details = "\n".join(f"  {error}" for error in self.errors)
        super().__init__(
            f"Rollback recovery incomplete for {len(self.errors)} journals:\n{details}"
        )


def rollback_error_for(exception: BaseException) -> JournalError | None:
    """Return rollback recovery failure attached to a primary exception."""
    value = getattr(exception, _ROLLBACK_ERROR_ATTR, None)
    return value if isinstance(value, JournalError) else None


def attach_rollback_error(
    primary: BaseException,
    rollback_error: JournalError,
) -> BaseException:
    """Attach rollback failure context while preserving the primary exception."""
    setattr(primary, _ROLLBACK_ERROR_ATTR, rollback_error)
    add_note = getattr(primary, "add_note", None)
    if callable(add_note):
        add_note(f"Rollback recovery also failed:\n{rollback_error}")
    return primary


class JournalState(str, Enum):
    """Lifecycle state for one named rollback journal."""

    OPEN = "open"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"


class MutationState(str, Enum):
    """Lifecycle state for one logical mutation entry."""

    PREPARED = "prepared"
    MUTATED = "mutated"
    APPLIED = "applied"
    ROLLED_BACK = "rolled_back"


@dataclass
class JournalEntry:
    """One logical mutation recorded in a rollback journal."""

    sequence: int
    kind: str
    state: MutationState = MutationState.PREPARED
    data: dict[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "kind": self.kind,
            "state": self.state.value,
            "data": self.data,
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "JournalEntry":
        return cls(
            sequence=int(value["sequence"]),
            kind=str(value["kind"]),
            state=MutationState(str(value["state"])),
            data=dict(value.get("data") or {}),
        )


@dataclass
class Journal:
    """Persistent state for one named rollback journal."""

    name: str
    state: JournalState = JournalState.OPEN
    entries: list[JournalEntry] = field(default_factory=list)

    @property
    def applied_entries(self) -> list[JournalEntry]:
        return [entry for entry in self.entries if entry.state is MutationState.APPLIED]

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "state": self.state.value,
            "entries": [entry.as_dict() for entry in self.entries],
        }

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "Journal":
        return cls(
            name=str(value["name"]),
            state=JournalState(str(value["state"])),
            entries=[
                JournalEntry.from_dict(dict(entry))
                for entry in value.get("entries") or []
            ],
        )


class JournalManager:
    """Manage rollback journals within one execution/session namespace."""

    def __init__(self, root: str | Path, *, session_id: str | None = None):
        self.root = Path(root).expanduser()
        self.session_id = session_id or uuid.uuid4().hex
        self.session_root = self.root / self.session_id
        self._journals: dict[str, Journal] = {}

    @staticmethod
    def validate_name(name: str) -> str:
        value = str(name).strip()
        if not value or not _JOURNAL_NAME.fullmatch(value):
            raise ValueError(f"Invalid rollback journal name: {name!r}")
        return value

    def _directory(self, name: str) -> Path:
        return self.session_root / self.validate_name(name)

    def _manifest(self, name: str) -> Path:
        return self._directory(name) / "manifest.json"

    def entry_storage(self, name: str, sequence: int) -> Path:
        """Return private storage assigned to one journal mutation entry."""
        journal = self.require_open(name)
        entry = self._entry(journal, sequence)
        return self._directory(journal.name) / "entries" / f"{entry.sequence:06d}"

    def _persist(self, journal: Journal) -> None:
        directory = self._directory(journal.name)
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.session_root.chmod(0o700)
        directory.chmod(0o700)
        temporary = directory / ".manifest.json.tmp"
        payload = json.dumps(journal.as_dict(), indent=2, sort_keys=True) + "\n"
        temporary.write_text(payload, encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(directory / "manifest.json")

    def _load(self, name: str) -> Journal | None:
        name = self.validate_name(name)
        manifest = self._manifest(name)
        try:
            payload = json.loads(manifest.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        journal = Journal.from_dict(payload)
        if journal.name != name:
            raise JournalError(
                f"Rollback journal manifest name mismatch: expected {name!r}, "
                f"found {journal.name!r}"
            )
        self._journals[name] = journal
        return journal

    def get(self, name: str) -> Journal | None:
        name = self.validate_name(name)
        journal = self._journals.get(name)
        return journal if journal is not None else self._load(name)

    def require_open(self, name: str) -> Journal:
        journal = self.get(name)
        if journal is None:
            raise JournalError(f"Rollback journal {name!r} is not open")
        if journal.state is not JournalState.OPEN:
            raise JournalError(
                f"Rollback journal {name!r} is {journal.state.value}, not open"
            )
        return journal

    def prepare(
        self,
        name: str,
        *,
        kind: str = "filesystem",
        data: dict[str, object] | None = None,
    ) -> JournalEntry:
        """Open a journal on demand and append one PREPARED mutation."""
        name = self.validate_name(name)
        journal = self.get(name)
        if journal is None:
            journal = Journal(name=name)
            self._journals[name] = journal
            info("opened rollback journal %r", name)
        elif journal.state is not JournalState.OPEN:
            raise JournalError(
                f"Rollback journal {name!r} is {journal.state.value}, not open"
            )

        debug(
            "transaction prepare journal=%s kind=%s sequence=%s",
            name,
            kind,
            len(journal.entries) + 1,
        )
        entry = JournalEntry(
            sequence=len(journal.entries) + 1,
            kind=str(kind),
            data=dict(data or {}),
        )
        journal.entries.append(entry)
        self._persist(journal)
        return entry

    def prepare_paths(
        self,
        name: str,
        *,
        operation: str,
        paths: list[str | Path] | tuple[str | Path, ...],
        identity=None,
    ) -> JournalEntry:
        """Prepare one filesystem mutation by capturing all affected paths."""
        from .identity import ExecutionIdentity
        from .snapshot import capture_path

        captured_paths = list(paths)
        if not captured_paths:
            raise ValueError("filesystem mutation requires at least one path")

        normalized_identity = (
            identity if isinstance(identity, ExecutionIdentity) else ExecutionIdentity()
        )
        entry = self.prepare(
            name,
            kind="filesystem",
            data={
                "operation": operation,
                "identity": normalized_identity.as_dict(),
                "paths": [],
            },
        )
        storage = self.entry_storage(name, entry.sequence)
        snapshots = []
        for index, path in enumerate(captured_paths):
            relative_storage = Path("paths") / f"{index:06d}"
            snapshot = capture_path(
                path,
                storage / relative_storage,
                identity=normalized_identity,
            )
            snapshot["storage"] = str(relative_storage)
            snapshots.append(snapshot)

        return self.update_entry_data(
            name,
            entry.sequence,
            {
                "operation": operation,
                "identity": normalized_identity.as_dict(),
                "paths": snapshots,
            },
        )

    def prepare_path(
        self,
        name: str,
        *,
        operation: str,
        path: str | Path,
        identity=None,
    ) -> JournalEntry:
        """Prepare one filesystem mutation by capturing a single path."""
        return self.prepare_paths(
            name,
            operation=operation,
            paths=(path,),
            identity=identity,
        )

    def update_entry_data(
        self,
        name: str,
        sequence: int,
        data: dict[str, object],
    ) -> JournalEntry:
        """Replace one PREPARED entry's persisted mutation data."""
        journal = self.require_open(name)
        entry = self._entry(journal, sequence)
        if entry.state is not MutationState.PREPARED:
            raise JournalError(
                f"Rollback journal {name!r} entry {sequence} is "
                f"{entry.state.value}, not prepared"
            )
        entry.data = dict(data)
        self._persist(journal)
        return entry

    def mark_mutated(self, name: str, sequence: int) -> JournalEntry:
        """Record that the forward mutation completed before post-state sealing."""
        journal = self.require_open(name)
        entry = self._entry(journal, sequence)
        if entry.state is not MutationState.PREPARED:
            raise JournalError(
                f"Rollback journal {name!r} entry {sequence} is "
                f"{entry.state.value}, not prepared"
            )
        entry.state = MutationState.MUTATED
        debug(
            "transaction mutated journal=%s sequence=%s operation=%s",
            name,
            sequence,
            entry.data.get("operation"),
        )
        self._persist(journal)
        return entry

    def mark_applied(self, name: str, sequence: int) -> JournalEntry:
        journal = self.require_open(name)
        entry = self._entry(journal, sequence)
        if entry.state is MutationState.PREPARED:
            entry = self.mark_mutated(name, sequence)
        elif entry.state is not MutationState.MUTATED:
            raise JournalError(
                f"Rollback journal {name!r} entry {sequence} is "
                f"{entry.state.value}, not mutated"
            )

        if entry.kind == "filesystem" and "paths" in entry.data:
            from .identity import ExecutionIdentity
            from .snapshot import fingerprint_path

            identity = ExecutionIdentity.from_dict(entry.data.get("identity"))
            paths = list(entry.data.get("paths") or [])
            entry.data["expected"] = [
                fingerprint_path(
                    str(snapshot["path"]),
                    identity=identity,
                )
                for snapshot in paths
            ]

        entry.state = MutationState.APPLIED
        debug(
            "transaction applied journal=%s sequence=%s operation=%s",
            name,
            sequence,
            entry.data.get("operation"),
        )
        self._persist(journal)
        return entry

    def verify_applied(self, name: str, sequence: int) -> JournalEntry:
        """Verify that an applied filesystem entry has not drifted."""
        journal = self.require_open(name)
        entry = self._entry(journal, sequence)
        if entry.state is not MutationState.APPLIED:
            raise JournalError(
                f"Rollback journal {name!r} entry {sequence} is "
                f"{entry.state.value}, not applied"
            )
        if entry.kind == "filesystem" and "expected" in entry.data:
            from .identity import ExecutionIdentity
            from .snapshot import verify_fingerprint

            identity = ExecutionIdentity.from_dict(entry.data.get("identity"))
            for expected in entry.data.get("expected") or []:
                verify_fingerprint(dict(expected), identity=identity)
        return entry

    def mark_rolled_back(self, name: str, sequence: int) -> JournalEntry:
        journal = self.require_open(name)
        entry = self._entry(journal, sequence)
        if entry.state is not MutationState.APPLIED:
            raise JournalError(
                f"Rollback journal {name!r} entry {sequence} is "
                f"{entry.state.value}, not applied"
            )
        entry.state = MutationState.ROLLED_BACK
        self._persist(journal)
        return entry

    def rollback_entry(self, name: str, sequence: int) -> JournalEntry:
        """Restore one APPLIED logical mutation after verifying all of its paths."""
        journal = self.require_open(name)
        entry = self._entry(journal, sequence)
        if entry.state is MutationState.MUTATED:
            raise JournalError(
                f"Rollback journal {name!r} entry {sequence} cannot be rolled back "
                "safely because its post-mutation fingerprint is unavailable"
            )
        if entry.state is not MutationState.APPLIED:
            raise JournalError(
                f"Rollback journal {name!r} entry {sequence} is "
                f"{entry.state.value}, not applied"
            )
        if entry.kind != "filesystem":
            raise JournalError(
                f"Rollback journal {name!r} entry {sequence} has unsupported "
                f"kind {entry.kind!r}"
            )

        from .identity import ExecutionIdentity
        from .snapshot import restore_path

        identity = ExecutionIdentity.from_dict(entry.data.get("identity"))
        snapshots = [dict(value) for value in entry.data.get("paths") or []]
        expected = [dict(value) for value in entry.data.get("expected") or []]
        if len(expected) != len(snapshots):
            raise JournalError(
                f"Rollback journal {name!r} entry {sequence} has incomplete "
                "post-mutation fingerprints"
            )
        for snapshot in snapshots:
            if snapshot.get("storage") is None:
                raise JournalError(
                    f"Rollback journal {name!r} entry {sequence} snapshot "
                    "has no storage location"
                )

        self.verify_applied(name, sequence)

        storage = self.entry_storage(name, sequence)
        for snapshot in reversed(snapshots):
            debug(
                "transaction rollback journal=%s sequence=%s operation=%s path=%s",
                name,
                sequence,
                entry.data.get("operation"),
                snapshot["path"],
            )
            restore_path(
                snapshot,
                storage / str(snapshot["storage"]),
                identity=identity,
            )

        return self.mark_rolled_back(name, sequence)

    def rollback_after_failure(
        self,
        name: str,
        primary: BaseException,
    ) -> BaseException:
        """Attempt rollback while preserving a forward failure as primary."""
        try:
            self.rollback(name)
        except JournalError as rollback_error:
            attach_rollback_error(primary, rollback_error)
        return primary

    def rollback(self, name: str) -> None:
        """Attempt every APPLIED journal entry in LIFO order."""
        journal = self.require_open(name)
        info("rolling back journal %r", journal.name)

        pending = [
            entry
            for entry in reversed(journal.entries)
            if entry.state in {MutationState.APPLIED, MutationState.MUTATED}
        ]
        failures = []
        for entry in pending:
            try:
                self.rollback_entry(name, entry.sequence)
            except Exception as exception:
                failure = RollbackFailure(
                    journal=journal.name,
                    sequence=entry.sequence,
                    operation=(
                        str(entry.data.get("operation"))
                        if entry.data.get("operation") is not None
                        else None
                    ),
                    error=exception,
                )
                failures.append(failure)
                error(
                    "rollback failure journal=%s sequence=%s operation=%s: %s",
                    failure.journal,
                    failure.sequence,
                    failure.operation or "unknown",
                    failure.error,
                )

        if failures:
            aggregate = RollbackError(
                journal.name,
                failures,
                attempted=len(pending),
            )
            error(
                "rollback journal %r incomplete: %s of %s entries failed",
                journal.name,
                len(failures),
                len(pending),
            )
            raise aggregate

        self.close_rolled_back(name)
        info("rolled back journal %r", name)

    @staticmethod
    def _entry(journal: Journal, sequence: int) -> JournalEntry:
        try:
            index = int(sequence) - 1
        except (TypeError, ValueError):
            index = -1
        if index < 0 or index >= len(journal.entries):
            raise JournalError(
                f"Rollback journal {journal.name!r} has no entry {sequence}"
            )
        return journal.entries[index]

    def commit(self, name: str) -> None:
        """Commit a non-empty journal and discard its persisted state."""
        journal = self.require_open(name)
        if any(entry.state is MutationState.MUTATED for entry in journal.entries):
            raise JournalError(
                f"Rollback journal {journal.name!r} has unsealed mutations "
                "and cannot be committed"
            )
        if not journal.applied_entries:
            raise JournalError(
                f"Rollback journal {journal.name!r} has no applied mutations to commit"
            )
        journal.state = JournalState.COMMITTED
        info("committed rollback journal %r", journal.name)
        self._discard(journal.name)

    def close_rolled_back(self, name: str) -> None:
        """Close a journal after all applied entries have been restored."""
        journal = self.require_open(name)
        if any(
            entry.state in {MutationState.APPLIED, MutationState.MUTATED}
            for entry in journal.entries
        ):
            raise JournalError(
                f"Rollback journal {journal.name!r} still has unresolved mutations"
            )
        journal.state = JournalState.ROLLED_BACK
        self._discard(journal.name)

    def open_names(self) -> tuple[str, ...]:
        """Return open journals in stable creation/discovery order."""
        names = list(self._journals)
        known = set(names)
        if self.session_root.is_dir():
            names.extend(
                sorted(
                    path.name
                    for path in self.session_root.iterdir()
                    if path.is_dir() and path.name not in known
                )
            )
        open_names = []
        for name in names:
            journal = self.get(name)
            if journal is not None and journal.state is JournalState.OPEN:
                open_names.append(name)
        return tuple(open_names)

    def _discard(self, name: str) -> None:
        self._journals.pop(name, None)
        shutil.rmtree(self._directory(name), ignore_errors=True)
        try:
            self.session_root.rmdir()
        except OSError:
            pass
