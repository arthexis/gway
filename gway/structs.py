# file: gway/structs.py

import collections


class Results(collections.ChainMap):
    """Request-owned semantic results with chronological history."""

    def __init__(self):
        super().__init__({})
        self.history = []

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

    def subject(self, value, default=None):
        """Return the most recent semantic subject bound to this exact value."""
        for subject, candidate in reversed(tuple(self.maps[0].items())):
            if candidate is value:
                return subject
        return default

    def get_results(self):
        return self.maps[0]
