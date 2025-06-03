# gway/watchers.py

import os
import time
import hashlib
import threading
import requests


def watch_file(filepath, on_change, *, poll_interval=10.0, hash=False):
    stop_event = threading.Event()

    def _watch():
        try:
            last_mtime = os.path.getmtime(filepath)
            last_hash = hashlib.md5(open(filepath, 'rb').read()).hexdigest() if hash else None
        except FileNotFoundError:
            last_mtime = None
            last_hash = None

        while not stop_event.is_set():
            try:
                current_mtime = os.path.getmtime(filepath)
                if hash:
                    if current_mtime != last_mtime:
                        with open(filepath, 'rb') as f:
                            current_hash = hashlib.md5(f.read()).hexdigest()
                        if last_hash and current_hash != last_hash:
                            on_change()
                            os._exit(1)
                        last_hash = current_hash
                    last_mtime = current_mtime
                else:
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
