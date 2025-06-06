# gway/watchers.py

import os
import time
import hashlib
import threading
import requests

def watch_file(*filepaths, on_change, poll_interval=10.0, hash=False, resource=True):
    from gway import gw

    paths = []
    for path in filepaths:
        resolved = gw.resource(path) if resource else path
        if os.path.isdir(resolved):
            for root, _, files in os.walk(resolved):
                for file in files:
                    paths.append(os.path.join(root, file))
        else:
            paths.append(resolved)

    stop_event = threading.Event()

    def _watch():
        last_mtimes = {}
        last_hashes = {}

        for path in paths:
            try:
                last_mtimes[path] = os.path.getmtime(path)
                if hash:
                    with open(path, 'rb') as f:
                        last_hashes[path] = hashlib.md5(f.read()).hexdigest()
            except FileNotFoundError:
                pass

        while not stop_event.is_set():
            for path in paths:
                try:
                    current_mtime = os.path.getmtime(path)
                    if hash:
                        if path not in last_mtimes or current_mtime != last_mtimes[path]:
                            with open(path, 'rb') as f:
                                current_hash = hashlib.md5(f.read()).hexdigest()
                            if path in last_hashes and current_hash != last_hashes[path]:
                                on_change()
                                os._exit(1)
                            last_hashes[path] = current_hash
                        last_mtimes[path] = current_mtime
                    else:
                        if path in last_mtimes and current_mtime != last_mtimes[path]:
                            on_change()
                            os._exit(1)
                        last_mtimes[path] = current_mtime
                except FileNotFoundError:
                    pass
            time.sleep(poll_interval)

    thread = threading.Thread(target=_watch, daemon=True)
    thread.start()
    return stop_event


def watch_url(url, on_change, *, 
              poll_interval=60.0, event="change", resend=False, value=None):
    stop_event = threading.Event()

    def _watch():
        last_hash = None
        while not stop_event.is_set():
            try:
                response = requests.get(url, timeout=5)
                content = response.content
                status_ok = 200 <= response.status_code < 400

                if event == "up":
                    if status_ok:
                        on_change()
                        os._exit(1)
                elif event == "down":
                    if not status_ok:
                        on_change()
                        os._exit(1)
                elif event == "has" and isinstance(value, str):
                    if value.lower() in content.decode(errors="ignore").lower():
                        on_change()
                        os._exit(1)
                elif event == "lacks" and isinstance(value, str):
                    if value.lower() not in content.decode(errors="ignore").lower():
                        on_change()
                        os._exit(1)
                else:  # event == "change"
                    response.raise_for_status()
                    current_hash = hashlib.sha256(content).hexdigest()
                    if last_hash is not None and current_hash != last_hash:
                        on_change()
                        os._exit(1)
                    last_hash = current_hash
            except Exception:
                pass
            time.sleep(poll_interval)

    thread = threading.Thread(target=_watch, daemon=True)
    thread.start()
    return stop_event


def watch_pypi_package(package_name, on_change, *, poll_interval=2500.0):
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
