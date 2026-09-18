"""Live registry of executable GWAY operations."""

from collections.abc import Mapping


class Operations(Mapping):
    """Mapping-like registry of operations currently available to a Gateway."""

    def __init__(self):
        self._items = {}

    def register(self, name, operation):
        if not callable(operation):
            raise TypeError(f"{name!r} is not callable")
        self._items[name] = operation
        return operation

    def unregister(self, name):
        return self._items.pop(name)

    def __getitem__(self, name):
        return self._items[name]

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)
