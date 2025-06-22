# file: gway/runner.py

import os
import time
import asyncio
import hashlib
import threading
import requests

from regex import W


# Extract all async/thread/coroutine runner logic into Runner,
# and have Gateway inherit from Runner and Resolver.
class Runner:
    """
    Runner provides async/threading/coroutine management for Gateway.
    """
    def __init__(self, *args, **kwargs):
        self._async_threads = []
        super().__init__(*args, **kwargs)

    def run_coroutine(self, func_name, coro_or_func, args=None, kwargs=None):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            if asyncio.iscoroutine(coro_or_func):
                result = loop.run_until_complete(coro_or_func)
            else:
                result = loop.run_until_complete(coro_or_func(*(args or ()), **(kwargs or {})))

            # Insert result into results if available (only if called from Gateway)
            if hasattr(self, "results"):
                self.results.insert(func_name, result)
                if isinstance(result, dict) and hasattr(self, "context"):
                    self.context.update(result)
        except Exception as e:
            if hasattr(self, "error"):
                self.error(f"Async error in {func_name}: {e}")
                if hasattr(self, "exception"):
                    self.exception(e)
        finally:
            loop.close()

    def until(self, *, file=None, url=None, pypi=False, forever=False, hours=None):
        assert file or url or pypi or forever, "Use forever for unconditional looping."

        # TODO: Implement an 'hours' param that allows a range of hours of operation
        # which may be in the form: 9:00 - 18:00 (with or w/o whitespace)
        # When the closing time is reached, stop the loop. If the function is requested
        # to start before the opening time, hold until that time before actually
        # starting (show a warning explaining its temporarily closed and hours)

        def shutdown(reason):
            if hasattr(self, "warning"):
                self.warning(f"{reason} triggered async shutdown.")
            os._exit(1)

        watchers = [
            (file, watch_file, "Lock file"),
            (url, watch_url, "Lock url"),
            (pypi if pypi is not False else None, watch_pypi_package, "PyPI package")
        ]
        for target, watcher, reason in watchers:
            if target:
                if hasattr(self, "info"):
                    self.info(f"Setup watcher for {reason}")
                if target is True and pypi:
                    target = "gway"
                watcher(target, on_change=lambda r=reason: shutdown(r))
        try:
            while any(thread.is_alive() for thread in self._async_threads):
                time.sleep(0.1)
        except KeyboardInterrupt:
            if hasattr(self, "critical"):
                self.critical("KeyboardInterrupt received. Exiting immediately.")
            os._exit(1)

    def forever(self): self.until(forever=True)


def watch_file(*filepaths, on_change, interval=10.0, hash=False, resource=True):
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
            time.sleep(interval)

    thread = threading.Thread(target=_watch, daemon=True)
    thread.start()
    return stop_event


def _retry_loop(fn, *, interval, stop_event, label):
    """Retry wrapper that logs and silently recovers from errors."""
    from gway import gw
    while not stop_event.is_set():
        try:
            fn()
        except Exception as e:
            gw.warn(f"[Watcher] {label} error: {e}")
        time.sleep(interval)


def watch_url(url, on_change, *, 
              interval=60.0, event="change", resend=False, value=None):
    stop_event = threading.Event()

    def _check():
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
            nonlocal last_hash
            current_hash = hashlib.sha256(content).hexdigest()
            if last_hash is not None and current_hash != last_hash:
                on_change()
                os._exit(1)
            last_hash = current_hash

    last_hash = None
    thread = threading.Thread(target=lambda: _retry_loop(
        _check, interval=interval, stop_event=stop_event, label=f"url:{url}"), daemon=True)
    thread.start()
    return stop_event


def watch_pypi_package(package_name, on_change, *, interval=3000.0):
    stop_event = threading.Event()
    url = f"https://pypi.org/pypi/{package_name}/json"

    def _check():
        nonlocal last_version
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        data = response.json()
        current_version = data["info"]["version"]
        if last_version is not None and current_version != last_version:
            on_change()
            os._exit(1)
        last_version = current_version

    last_version = None
    thread = threading.Thread(target=lambda: _retry_loop(
        _check, interval=interval, stop_event=stop_event, label=f"pypi:{package_name}"), daemon=True)
    thread.start()
    return stop_event
