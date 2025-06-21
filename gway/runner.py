# file: gway/runner.py

import os
import time
import asyncio

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

    def until(self, *, file=None, url=None, pypi=False, forever=False):
        assert file or url or pypi or forever, "Use forever for unconditional looping."

        from .watchers import watch_file, watch_url, watch_pypi_package

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