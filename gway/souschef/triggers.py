"""Trigger evaluation for Sous Chef."""

import hashlib
from pathlib import Path
import time

from .scheduler import Scheduler
from .state import StateStore


def watch_token(path):
    """Return a stable observable token for one watched file."""
    path = Path(path)
    try:
        if not path.is_file():
            return "missing"
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return f"file:{digest.hexdigest()}"
    except OSError as exc:
        return f"error:{type(exc).__name__}:{exc}"


class TriggerEngine:
    """Evaluate Sous Chef triggers and enqueue eligible jobs."""

    def __init__(
        self,
        jobs=(),
        *,
        scheduler=None,
        state_root,
        service_status=None,
        clock=None,
    ):
        self.jobs = {job.identity: job for job in jobs}
        self.state = StateStore(state_root)
        self.service_status = service_status
        self.clock = clock or time.time
        self.scheduler = scheduler or Scheduler(jobs)
        self.scheduler.on_started = self._started
        self.scheduler.on_completed = self._completed
        self._restore_pending()

    def _restore_pending(self):
        for job in self.jobs.values():
            state = self.state.get(*job.identity)
            interrupted = (
                state.last_started is not None
                and (
                    state.last_completed is None
                    or state.last_completed < state.last_started
                )
            )
            if state.pending or interrupted:
                self.scheduler.enqueue(job, "resume")

    def _started(self, job, reasons):
        state = self.state.get(*job.identity)
        state.last_started = float(self.clock())
        state.pending = False
        self.state.put(state)

    def _completed(self, result):
        state = self.state.get(*result.job.identity)
        now = float(self.clock())
        state.last_completed = now
        if result.success:
            state.last_success = now
        else:
            state.last_failure = now
        state.pending = any(
            pending.identity == result.job.identity
            for pending in self.scheduler.pending
        )
        self.state.put(state)

    def _service_down(self, target):
        if self.service_status is None or "://" in target:
            return False
        if "/" not in target:
            return False
        project, service = target.split("/", 1)
        if not project or not service:
            return False
        try:
            status = self.service_status(project, service)
        except LookupError:
            return True
        return not bool(status.get("running"))

    def evaluate_job(self, job):
        """Evaluate one job and enqueue any newly satisfied trigger reasons."""
        state = self.state.get(*job.identity)
        now = float(self.clock())
        reasons = []

        if job.every is not None:
            if (
                state.last_started is None
                or now - state.last_started >= job.every
            ):
                reasons.append("every")

        if job.watch is not None:
            current = watch_token(job.watch)
            if state.watch_token is None:
                state.watch_token = current
            elif current != state.watch_token:
                state.watch_token = current
                reasons.append("watch")

        if job.down is not None:
            current_down = self._service_down(job.down)
            if current_down and state.down_state is not True:
                reasons.append("down")
            state.down_state = current_down

        for reason in reasons:
            self.scheduler.enqueue(job, reason)

        if reasons:
            state.pending = True
        self.state.put(state)
        return tuple(reasons)

    def evaluate(self):
        """Evaluate every registered job once."""
        return {
            job.identity: self.evaluate_job(job)
            for job in self.jobs.values()
        }
