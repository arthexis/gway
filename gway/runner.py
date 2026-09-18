# file: gway/runner.py

import asyncio
import re
import time


class Runner:
    """Core callable and coroutine execution support."""

    def _resolve_callable(self, value):
        if callable(value):
            return value

        key = re.sub(r"^(gw|gway)[. ]+", "", str(value).strip())
        candidate = self.get(key)
        if callable(candidate):
            return candidate

        obj = self
        for part in re.split(r"[. ]+", key):
            obj = getattr(obj, part)
        if not callable(obj):
            raise TypeError(f"{value!r} did not resolve to a callable")
        return obj

    def run_coroutine(self, func_name, coroutine):
        """Run an awaitable synchronously at the runtime boundary."""
        start = time.perf_counter() if getattr(self, "timed_enabled", False) else None
        loop = asyncio.new_event_loop()
        try:
            asyncio.set_event_loop(loop)
            result = loop.run_until_complete(coroutine)
            if hasattr(self, "results"):
                self.results.insert(func_name, result)
                if isinstance(result, dict) and hasattr(self, "context"):
                    self.context.update(result)
            return result
        finally:
            loop.close()
            if start is not None and hasattr(self, "logger"):
                self.logger.info(
                    "[timed] %s took %.3fs",
                    func_name,
                    time.perf_counter() - start,
                )
