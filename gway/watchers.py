import os
import time
import hashlib
import threading

from .decorators import requires


def watch_file(filepath, on_change, poll_interval=5.0):
    stop_event = threading.Event()

    def _watch():
        try:
            last_mtime = os.path.getmtime(filepath)
        except FileNotFoundError:
            last_mtime = None

        while not stop_event.is_set():
            try:
                current_mtime = os.path.getmtime(filepath)
                if last_mtime is not None and current_mtime != last_mtime:
                    on_change()
                    os._exit(1)
                last_mtime = current_mtime
            except FileNotFoundError:
                pass
            time.sleep(poll_interval)

    thread = threading.Thread(target=_watch, daemon=True)
    thread.start()
    return stop_event


@requires("requests")
def watch_url(url, on_change, poll_interval=30.0):
    import threading
    import requests

    stop_event = threading.Event()

    def _watch():
        last_hash = None
        while not stop_event.is_set():
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            current_hash = hashlib.sha256(response.content).hexdigest()

            if last_hash is not None and current_hash != last_hash:
                on_change()
                os._exit(1)

            last_hash = current_hash
            time.sleep(poll_interval)

    thread = threading.Thread(target=_watch, daemon=True)
    thread.start()
    return stop_event


@requires("requests")
def watch_pypi_package(package_name, on_change, poll_interval=300.0):
    import threading
    import requests

    url = f"https://pypi.org/pypi/{package_name}/json"
    stop_event = threading.Event()

    def _watch():
        last_version = None
        while not stop_event.is_set():
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            data = response.json()
            current_version = data["info"]["version"]

            if last_version is not None and current_version != last_version:
                on_change()
                os._exit(1)

            last_version = current_version
            time.sleep(poll_interval)

    thread = threading.Thread(target=_watch, daemon=True)
    thread.start()
    return stop_event
