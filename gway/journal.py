"""Invocation-scoped rollback journal state and persistence."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
import re
import shutil
import uuid


_JOURNAL_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class JournalError(RuntimeError):
    """Base error for rollback journal lifecycle violations."""


class JournalState(str, Enum):
    """Lifecycle state for one named rollback journal."""

    OPEN = "open"
    COMMITTED = "committed"
    ROLLED_BACK = "rolled_back"


class MutationState(str, Enum):
    """Lifecycle state for one logical mutation entry."""

    PREPARED = "prepared"
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

    def _persist(self, journal: Journal) -> None:
        directory = self._directory(journal.name)
        directory.mkdir(parents=True, exist_ok=True)
        temporary = directory / ".manifest.json.tmp"
        payload = json.dumps(journal.as_dict(), indent=2, sort_keys=True) + "\n"
        temporary.write_text(payload, encoding="utf-8")
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
        elif journal.state is not JournalState.OPEN:
            raise JournalError(
                f"Rollback journal {name!r} is {journal.state.value}, not open"
            )

        entry = JournalEntry(
            sequence=len(journal.entries) + 1,
            kind=str(kind),
            data=dict(data or {}),
        )
        journal.entries.append(entry)
        self._persist(journal)
        return entry

    def mark_applied(self, name: str, sequence: int) -> JournalEntry:
        journal = self.require_open(name)
        entry = self._entry(journal, sequence)
        if entry.state is not MutationState.PREPARED:
            raise JournalError(
                f"Rollback journal {name!r} entry {sequence} is "
                f"{entry.state.value}, not prepared"
            )
        entry.state = MutationState.APPLIED
        self._persist(journal)
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

    @staticmethod
    def _entry(journal: Journal, sequence: int) -> JournalEntry:
        try:
            return journal.entries[int(sequence) - 1]
        except (IndexError, ValueError):
            raise JournalError(
                f"Rollback journal {journal.name!r} has no entry {sequence}"
            ) from None

    def commit(self, name: str) -> None:
        """Commit a non-empty journal and discard its persisted state."""
        journal = self.require_open(name)
        if not journal.applied_entries:
            raise JournalError(
                f"Rollback journal {journal.name!r} has no applied mutations to commit"
            )
        journal.state = JournalState.COMMITTED
        self._discard(journal.name)

    def close_rolled_back(self, name: str) -> None:
        """Close a journal after all applied entries have been restored."""
        journal = self.require_open(name)
        if any(entry.state is MutationState.APPLIED for entry in journal.entries):
            raise JournalError(
                f"Rollback journal {journal.name!r} still has applied mutations"
            )
        journal.state = JournalState.ROLLED_BACK
        self._discard(journal.name)

    def open_names(self) -> tuple[str, ...]:
        names = set(self._journals)
        if self.session_root.is_dir():
            names.update(path.name for path in self.session_root.iterdir() if path.is_dir())
        open_names = []
        for name in sorted(names):
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
