"""Single-worker scheduling core for Sous Chef."""

from collections import deque
from dataclasses import dataclass
import threading


@dataclass(frozen=True)
class RunResult:
    """Outcome of one scheduler-owned job execution."""

    job: object
    reasons: tuple[str, ...]
    success: bool
    value: object = None
    error: BaseException | None = None


class Scheduler:
    """Deduplicating, single-worker scheduler for Sous Chef jobs."""

    def __init__(
        self,
        jobs=(),
        *,
        executor=None,
        on_started=None,
        on_completed=None,
    ):
        self._jobs = {}
        self._queue = deque()
        self._pending = set()
        self._reasons = {}
        self._active = None
        self._lock = threading.RLock()
        self._run_lock = threading.Lock()
        if executor is None:
            from .executor import RecipeExecutor

            executor = RecipeExecutor()
        self.executor = executor
        self.on_started = on_started
        self.on_completed = on_completed
        self.add(jobs)

    @property
    def active(self):
        """Return the currently executing job, if any."""
        with self._lock:
            return self._active

    @property
    def pending(self):
        """Return pending jobs in execution order."""
        with self._lock:
            return tuple(self._jobs[identity] for identity in self._queue)

    def add(self, jobs):
        """Register jobs by durable project/job identity."""
        with self._lock:
            for job in jobs:
                existing = self._jobs.get(job.identity)
                if existing is not None and existing != job:
                    raise ValueError(
                        f"Duplicate Sous Chef job identity: {job.identity!r}"
                    )
                self._jobs[job.identity] = job
        return self

    def get(self, project, name):
        """Return one registered job."""
        try:
            return self._jobs[(project, name)]
        except KeyError as exc:
            raise LookupError(f"Unknown Sous Chef job {project!r}/{name!r}") from exc

    def enqueue(self, job, reason="manual"):
        """Queue one job once, coalescing additional trigger reasons."""
        identity = job.identity
        with self._lock:
            registered = self._jobs.get(identity)
            if registered is None:
                self._jobs[identity] = job
            elif registered != job:
                raise ValueError(f"Conflicting Sous Chef job identity: {identity!r}")

            reasons = self._reasons.setdefault(identity, [])
            if reason not in reasons:
                reasons.append(reason)

            if identity not in self._pending:
                self._queue.append(identity)
                self._pending.add(identity)
                return True
            return False

    def _take(self):
        with self._lock:
            if not self._queue:
                return None
            identity = self._queue.popleft()
            self._pending.remove(identity)
            job = self._jobs[identity]
            reasons = tuple(self._reasons.pop(identity, ()))
            self._active = job
            return job, reasons

    def run_next(self):
        """Execute at most one queued job.

        Concurrent callers serialize on the worker lock. Failures become
        RunResult values so a failed recipe never terminates the scheduler.
        """
        with self._run_lock:
            taken = self._take()
            if taken is None:
                return None

            job, reasons = taken
            if self.on_started is not None:
                self.on_started(job, reasons)
            result = None
            try:
                value = self.executor(job)
            except BaseException as exc:
                result = RunResult(
                    job=job,
                    reasons=reasons,
                    success=False,
                    error=exc,
                )
            else:
                result = RunResult(
                    job=job,
                    reasons=reasons,
                    success=True,
                    value=value,
                )
            finally:
                with self._lock:
                    self._active = None
            if self.on_completed is not None:
                self.on_completed(result)
            return result

    def drain(self):
        """Run queued jobs serially until no pending work remains."""
        results = []
        while True:
            result = self.run_next()
            if result is None:
                return results
            results.append(result)
