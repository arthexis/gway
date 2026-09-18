# file: gway/structs.py

import collections
import threading


class Results(collections.ChainMap):
    """Thread-local semantic results with chronological history."""

    _thread_local = threading.local()

    def __init__(self):
        if not hasattr(self._thread_local, "maps"):
            self._thread_local.maps = [{}]
        if not hasattr(self._thread_local, "history"):
            self._thread_local.history = []
        super().__init__(*self._thread_local.maps)
        self.history = self._thread_local.history

    def insert(self, name, value):
        """Record a result chronologically and, when named, by semantic subject."""
        self.history.append(value)
        if name is not None:
            self.maps[0][name] = value
        return value

    def __getitem__(self, key):
        if isinstance(key, int):
            return self.history[key]
        return super().__getitem__(key)

    def clear(self):
        self.maps[0].clear()
        self.history.clear()

    @property
    def last(self):
        return self.history[-1] if self.history else None

    def get_results(self):
        return self.maps[0]
