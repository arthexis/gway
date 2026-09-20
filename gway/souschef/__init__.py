"""Built-in Sous Chef recipe scheduler declarations."""

import signal
import threading

from ..install.paths import data_root
from .executor import RecipeExecutionError, RecipeExecutor, RecipeFailure, RecipeTimeoutError
from .manifest import duration, job_from_data, jobs_from_data, load
from .model import DEFAULT_TIMEOUT, Job
from .scheduler import RunResult, Scheduler
from .state import JobState, StateStore
from .triggers import TriggerEngine, watch_token

__all__ = [
    "DEFAULT_TIMEOUT",
    "Job",
    "RecipeExecutionError",
    "RecipeExecutor",
    "RecipeFailure",
    "RecipeTimeoutError",
    "RunResult",
    "Scheduler",
    "JobState",
    "StateStore",
    "TriggerEngine",
    "watch_token",
    "duration",
    "job_from_data",
    "jobs_from_data",
    "load",
]


def __main__(*, poll=1.0):
    """Run Sous Chef in the foreground until interrupted."""
    from ..gateway import Gateway

    runtime = Gateway()
    stop = threading.Event()

    def request_stop(signum, frame):
        stop.set()

    for name in ("SIGTERM", "SIGINT"):
        signum = getattr(signal, name, None)
        if signum is not None:
            signal.signal(signum, request_stop)

    jobs = tuple(getattr(runtime, "_souschef_jobs", {}).values())
    engine = TriggerEngine(
        jobs,
        state_root=data_root() / "souschef",
        service_status=runtime._service_controller.status,
    )

    while not stop.is_set():
        engine.evaluate()
        engine.scheduler.drain()
        stop.wait(poll)
    return 0
