"""Ordered sigil alternatives."""

from collections.abc import Sequence, Set

from .value import Sigil


class Spool:
    """Ordered alternatives of context-free Sigil values."""

    def __init__(self, *values):
        self.sigils = []
        for item in values:
            if item:
                self._add_flat(item)

    def _add_flat(self, item):
        if isinstance(item, Set) and not isinstance(item, (str, bytes, bytearray)):
            raise TypeError("Spool alternatives must preserve order")
        if isinstance(item, Sequence) and not isinstance(
            item, (str, bytes, bytearray, Sigil)
        ):
            for sub in item:
                self._add_flat(sub)
            return
        self.sigils.append(item if isinstance(item, Sigil) else Sigil(item))

    def resolve(self, resolver=None):
        if resolver is None:
            from gway import gw

            resolver = gw

        last_exc = None
        for sigil in self:
            try:
                return sigil.resolve(resolver)
            except KeyError as exc:
                last_exc = exc

        if last_exc:
            raise last_exc
        raise KeyError("Spool: No items to resolve.")

    def __getitem__(self, index):
        return self.sigils[index]

    def __len__(self):
        return len(self.sigils)

    def __iter__(self):
        return iter(self.sigils)

    def append(self, value):
        self._add_flat(value)

    def extend(self, values):
        self._add_flat(values)

    def index(self, value):
        value = value if isinstance(value, Sigil) else Sigil(value)
        return self.sigils.index(value)

    def count(self, value):
        value = value if isinstance(value, Sigil) else Sigil(value)
        return self.sigils.count(value)

    def __repr__(self):
        return f"Spool({', '.join(repr(sigil) for sigil in self.sigils)})"

    def __str__(self):
        return " | ".join(str(sigil) for sigil in self.sigils)


__ = Spool
