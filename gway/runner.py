# file: gway/runner.py

import os
import time
import asyncio
import hashlib
import threading
import requests


# Extract all async/thread/coroutine runner logic into Runner,
# and have Gateway inherit from Runner and Resolver.
class Runner:
    """
    Runner provides async/threading/coroutine management for Gateway.
    """
    def __init__(self, *args, **kwargs):
        self._async_threads = []
        super().__init__(*args, **kwargs)

    def _resolve_callable(self, name):
        if callable(name):
            return name
        obj = self
        for part in str(name).split('.'):
            obj = getattr(obj, part)
        return obj

    def run_coroutine(self, func_name, coro_or_func, args=None, kwargs=None):
        try:
            start_time = time.perf_counter() if getattr(self, 'timed_enabled', False) else None
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
            if start_time is not None:
                if hasattr(self, 'log'):
                    self.log(f"[timed] {func_name} (async) took {time.perf_counter() - start_time:.3f}s")

    def every(self, target, *args, interval=60, daemon=True, **kwargs):
        """Run ``target`` periodically every ``interval`` seconds."""
        func = self._resolve_callable(target)

        def loop():
            while True:
                try:
                    func(*args, **kwargs)
                except Exception as e:
                    if hasattr(self, "warn"):
                        self.warn(f"[every] {target} failed: {e}")
                time.sleep(interval)

        t = threading.Thread(target=loop, daemon=daemon)
        t.start()
        self._async_threads.append(t)
        return t

    def until(self, *, file=None, url=None, pypi=False, version=False, build=False,
              done=False, notify=False, notify_only=False, abort=False,
              minor=False, major=False):
        assert file or url or pypi or version or build or done, "Use --done for unconditional looping."

        if not self._async_threads and hasattr(self, "critical"):
            self.critical("No async threads detected before entering loop.")

        from gway import gw

        abort_triggered = False
        abort_message = None

        def shutdown(reason):
            message = f"{reason} triggered async shutdown."
            if notify or notify_only:
                try:
                    gw.notify(message)
                except Exception:
                    pass
            if notify_only:
                if hasattr(self, "warning"):
                    self.warning(message + " (notify-only)")
                return
            if hasattr(self, "warning"):
                self.warning(message)
            if abort:
                nonlocal abort_triggered, abort_message
                abort_triggered = True
                abort_message = message
            self._async_threads.clear()

        watchers = []
        if version:
            if minor or major:
                part = "major" if major else "minor"
                watchers.append((
                    gw.resource("VERSION"),
                    lambda t, on_change, p=part: watch_version(t, on_change, part=p),
                    "VERSION file",
                ))
            else:
                watchers.append((gw.resource("VERSION"), watch_file, "VERSION file"))
        if build:
            watchers.append((gw.resource("BUILD"), watch_file, "BUILD file"))
        watchers.extend([
            (file, watch_file, "Lock file"),
            (url, watch_url, "Lock url"),
            (pypi if pypi is not False else None, watch_pypi_package, "PyPI package"),
        ])
        events = []
        for target, watcher, reason in watchers:
            if target:
                if hasattr(self, "info"):
                    self.info(f"Setup watcher for {reason}")
                if target is True and pypi:
                    target = "gway"
                events.append(watcher(target, on_change=lambda r=reason: shutdown(r)))
        try:
            while True:
                # Discard finished threads
                self._async_threads[:] = [t for t in self._async_threads if t.is_alive()]

                if self._async_threads:
                    time.sleep(0.1)
                    continue

                # Keep looping if any watcher is still active
                if any(e and not e.is_set() for e in events):
                    time.sleep(0.1)
                    continue

                break
        except KeyboardInterrupt:
            if hasattr(self, "critical"):
                self.critical("KeyboardInterrupt received. Exiting immediately.")
            os._exit(1)
        finally:
            for e in events:
                if e:
                    e.set()
        if abort and abort_triggered:
            gw.abort(abort_message or "Async shutdown", exit_code=1)


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
                                stop_event.set()
                                return
                            last_hashes[path] = current_hash
                        last_mtimes[path] = current_mtime
                    else:
                        if path in last_mtimes and current_mtime != last_mtimes[path]:
                            on_change()
                            stop_event.set()
                            return
                        last_mtimes[path] = current_mtime
                except FileNotFoundError:
                    pass
            time.sleep(interval)

    thread = threading.Thread(target=_watch, daemon=True)
    thread.start()
    return stop_event


def watch_version(path, on_change, *, interval=10.0, part=None):
    """Watch VERSION file and trigger only on specific version part changes."""
    from gway import gw

    resolved = gw.resource(path)
    stop_event = threading.Event()

    def parse_version(vstr):
        parts = [p or '0' for p in vstr.strip().split('.')]
        while len(parts) < 3:
            parts.append('0')
        try:
            return [int(p) for p in parts[:3]]
        except Exception:
            return [0, 0, 0]

    def _watch():
        try:
            last_mtime = os.path.getmtime(resolved)
            with open(resolved) as f:
                last_version = parse_version(f.read())
        except FileNotFoundError:
            last_mtime = None
            last_version = None

        while not stop_event.is_set():
            try:
                current_mtime = os.path.getmtime(resolved)
                if last_mtime is None or current_mtime != last_mtime:
                    with open(resolved) as f:
                        current_version = parse_version(f.read())
                    changed = False
                    if last_version is not None:
                        if part == 'minor':
                            changed = current_version[1] != last_version[1]
                        elif part == 'major':
                            changed = current_version[0] != last_version[0]
                        else:
                            changed = current_version != last_version
                    last_mtime = current_mtime
                    last_version = current_version
                    if changed:
                        on_change()
                        stop_event.set()
                        return
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
              interval=300.0, event="change", resend=False, value=None):
    stop_event = threading.Event()

    def _check():
        response = requests.get(url, timeout=5)
        content = response.content
        status_ok = 200 <= response.status_code < 400

        if event == "up":
            if status_ok:
                on_change()
                stop_event.set()
                return
        elif event == "down":
            if not status_ok:
                on_change()
                stop_event.set()
                return
        elif event == "has" and isinstance(value, str):
            if value.lower() in content.decode(errors="ignore").lower():
                on_change()
                stop_event.set()
                return
        elif event == "lacks" and isinstance(value, str):
            if value.lower() not in content.decode(errors="ignore").lower():
                on_change()
                stop_event.set()
                return
        else:  # event == "change"
            response.raise_for_status()
            nonlocal last_hash
            current_hash = hashlib.sha256(content).hexdigest()
            if last_hash is not None and current_hash != last_hash:
                on_change()
                stop_event.set()
                return
            last_hash = current_hash

    last_hash = None
    thread = threading.Thread(target=lambda: _retry_loop(
        _check, interval=interval, stop_event=stop_event, label=f"url:{url}"), daemon=True)
    thread.start()
    return stop_event


def watch_pypi_package(package_name, on_change, *, interval=1800.0):
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
            stop_event.set()
            return
        last_version = current_version

    last_version = None
    thread = threading.Thread(target=lambda: _retry_loop(
        _check, interval=interval, stop_event=stop_event, label=f"pypi:{package_name}"), daemon=True)
    thread.start()
    return stop_event
