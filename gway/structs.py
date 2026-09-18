# file: gway/structs.py

import collections
import threading


class Results(collections.ChainMap):
    """Thread-local result collector used by Gateway."""

    _thread_local = threading.local()

    def __init__(self):
        if not hasattr(self._thread_local, "maps"):
            self._thread_local.maps = [{}]
        super().__init__(*self._thread_local.maps)

    def insert(self, name, value):
        if isinstance(value, dict):
            self.maps[0].update(value)
        else:
            self.maps[0][name] = value

    def get_results(self):
        return self.maps[0]
