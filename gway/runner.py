# file: gway/runner.py

import asyncio
import re
import time


class Runner:
    """Core execution support shared by Gateway."""

    def __init__(self, *args, **kwargs):
        self._async_threads = []
        super().__init__(*args, **kwargs)

    def _resolve_callable(self, name):
        """Return a callable from a dotted/space path or via Gateway lookup."""
        if callable(name):
            return name

        key = str(name).strip()
        key = re.sub(r"^(gw|gway)[. ]+", "", key)

        if hasattr(self, "__getitem__"):
            try:
                func = self[key]
                if callable(func):
                    return func
            except Exception:
                pass

        obj = self
        for part in re.split(r"[. ]+", key):
            obj = getattr(obj, part)
        return obj

    def run_coroutine(self, func_name, coro_or_func, args=None, kwargs=None):
        """Run one coroutine in an isolated event loop and publish its result."""
        start_time = time.perf_counter() if getattr(self, "timed_enabled", False) else None
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            if asyncio.iscoroutine(coro_or_func):
                result = loop.run_until_complete(coro_or_func)
            else:
                result = loop.run_until_complete(
                    coro_or_func(*(args or ()), **(kwargs or {}))
                )

            if hasattr(self, "results"):
                self.results.insert(func_name, result)
                if isinstance(result, dict) and hasattr(self, "context"):
                    self.context.update(result)
            return result
        except Exception as exc:
            if hasattr(self, "error"):
                self.error(f"Async error in {func_name}: {exc}")
                if hasattr(self, "exception"):
                    self.exception(exc)
            raise
        finally:
            loop.close()
            if start_time is not None and hasattr(self, "log"):
                self.log(
                    f"[timed] {func_name} (async) took "
                    f"{time.perf_counter() - start_time:.3f}s"
                )
