"""Portable subprocess supervisor for Gway services."""

import signal
import subprocess
import sys
import time


def supervise(command, *, restart="on-failure", attempts=3, restart_sec=5.0):
    """Run a command, applying the configured restart policy."""
    command = tuple(command)
    if not command:
        raise ValueError("supervisor requires a command")

    child = None
    stopping = False

    def forward(signum, frame):
        nonlocal stopping
        stopping = True
        if child is not None and child.poll() is None:
            try:
                child.send_signal(signum)
            except ProcessLookupError:
                pass

    previous = {}
    for name in ("SIGTERM", "SIGINT"):
        signum = getattr(signal, name, None)
        if signum is not None:
            previous[signum] = signal.getsignal(signum)
            signal.signal(signum, forward)

    try:
        remaining = int(attempts)
        while True:
            child = subprocess.Popen(command)
            returncode = child.wait()
            retry = restart == "always" or (restart == "on-failure" and returncode != 0)
            if stopping or not retry or remaining <= 0:
                return returncode
            remaining -= 1
            if restart_sec:
                time.sleep(float(restart_sec))
            if stopping:
                return returncode
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def main(argv=None):
    """Run the internal portable supervisor command line."""
    argv = list(sys.argv[1:] if argv is None else argv)
    restart = "on-failure"
    attempts = 3
    restart_sec = 5.0

    while argv:
        token = argv.pop(0)
        if token == "--restart":
            restart = argv.pop(0)
            continue
        if token == "--attempts":
            attempts = int(argv.pop(0))
            continue
        if token == "--restart-sec":
            restart_sec = float(argv.pop(0))
            continue
        if token == "--":
            break
        raise ValueError(f"Unknown supervisor option: {token}")

    if not argv:
        raise ValueError("supervisor requires a command after --")
    return supervise(
        argv,
        restart=restart,
        attempts=attempts,
        restart_sec=restart_sec,
    )


if __name__ == "__main__":
    raise SystemExit(main())
