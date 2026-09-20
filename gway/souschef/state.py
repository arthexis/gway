"""Durable Sous Chef trigger and run state."""

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile


@dataclass
class JobState:
    """Durable state needed to reconstruct one Sous Chef job."""

    project: str
    job: str
    last_started: float | None = None
    last_completed: float | None = None
    last_success: float | None = None
    last_failure: float | None = None
    watch_token: str | None = None
    down_state: bool | None = None
    pending: bool = False

    @property
    def identity(self):
        return self.project, self.job


class StateStore:
    """Atomic JSON state store keyed by project and job."""

    def __init__(self, root):
        self.root = Path(root).expanduser().resolve()

    def path(self, project, job):
        return self.root / project / f"{job}.json"

    def get(self, project, job):
        path = self.path(project, job)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return JobState(project=project, job=job)
        return JobState(
            project=project,
            job=job,
            last_started=data.get("last_started"),
            last_completed=data.get("last_completed"),
            last_success=data.get("last_success"),
            last_failure=data.get("last_failure"),
            watch_token=data.get("watch_token"),
            down_state=data.get("down_state"),
            pending=bool(data.get("pending", False)),
        )

    def put(self, state):
        path = self.path(state.project, state.job)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(
            prefix=f".{state.job}.",
            suffix=".tmp",
            dir=path.parent,
        )
        temp = Path(temporary)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(asdict(state), stream, sort_keys=True)
                stream.write("\n")
            os.replace(temp, path)
        finally:
            if temp.exists():
                temp.unlink()
        return state
