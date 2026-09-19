"""Long-running Sous Chef service entrypoint."""

import signal
import threading

from ..gateway import Gateway
from ..install.paths import data_root
from .triggers import TriggerEngine


def run(*, poll=1.0):
    """Run the built-in Sous Chef trigger loop until terminated."""
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


def __main__():
    """Run Sous Chef as a module/service entrypoint."""
    return run()


if __name__ == "__main__":
    raise SystemExit(__main__())
