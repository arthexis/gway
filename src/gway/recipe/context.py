from __future__ import annotations

from collections.abc import Iterator, Mapping, MutableMapping

from ..chain_context import current_chain_provenance
from ..provenance import ValueProvenance


class _LiveProvenance(MutableMapping[str, ValueProvenance]):
    """Sidecar provenance that invalidates entries when backing values change."""

    def __init__(
        self,
        values: MutableMapping[str, object],
        initial: Mapping[str, ValueProvenance] | None = None,
    ) -> None:
        self._values = values
        self._records: dict[str, tuple[ValueProvenance, object]] = {}
        for key, provenance in (initial or {}).items():
            if key in values:
                self._records[key] = (provenance, values[key])

    def _valid(self, key: str) -> bool:
        record = self._records.get(key)
        if record is None or key not in self._values:
            return False
        _, snapshot = record
        try:
            return self._values[key] == snapshot
        except Exception:
            return self._values[key] is snapshot

    def __getitem__(self, key: str) -> ValueProvenance:
        if not self._valid(key):
            self._records.pop(key, None)
            raise KeyError(key)
        return self._records[key][0]

    def __setitem__(self, key: str, value: ValueProvenance) -> None:
        if key not in self._values:
            self._records.pop(key, None)
            return
        self._records[key] = (value, self._values[key])

    def __delitem__(self, key: str) -> None:
        del self._records[key]

    def __iter__(self) -> Iterator[str]:
        for key in tuple(self._records):
            if self._valid(key):
                yield key
            else:
                self._records.pop(key, None)

    def __len__(self) -> int:
        return sum(1 for _ in self)


class RecipeContext(MutableMapping[str, object]):
    """Named recipe values backed by a live mapping with sidecar provenance."""

    def __init__(
        self,
        values: MutableMapping[str, object] | None = None,
        *,
        provenance: Mapping[str, ValueProvenance] | None = None,
    ) -> None:
        self._values: MutableMapping[str, object] = {} if values is None else values
        self.provenance: MutableMapping[str, ValueProvenance] = _LiveProvenance(
            self._values,
            provenance,
        )

    def __getitem__(self, key: str) -> object:
        return self._values[key]

    def __setitem__(self, key: str, value: object) -> None:
        self._values[key] = value
        self.provenance.pop(key, None)

    def __delitem__(self, key: str) -> None:
        del self._values[key]
        self.provenance.pop(key, None)

    def __iter__(self) -> Iterator[str]:
        return iter(self._values)

    def __len__(self) -> int:
        return len(self._values)


def child_recipe_context(
    parent: Mapping[str, object] | None = None,
    *,
    incoming: object = None,
    has_incoming: bool = False,
) -> RecipeContext:
    """Create an isolated child frame and explicitly publish chained input into it."""
    context = RecipeContext(dict(parent or {}), provenance=current_chain_provenance())
    if has_incoming:
        if isinstance(incoming, Mapping):
            context.update(incoming)
        context["result"] = incoming
    return context


__all__ = ["RecipeContext", "child_recipe_context"]
