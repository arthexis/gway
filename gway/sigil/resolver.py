"""Resolver policy and source precedence."""

from collections.abc import Mapping
import os
import re

from .paths import follow_path
from .resolution import resolve_text
from .value import Sigil

_MISSING = object()
_RAISE = object()


class Environment(Mapping):
    """Case-normalized view of an environment mapping for semantic lookup."""

    def __init__(self, environ=None):
        self._environ = os.environ if environ is None else environ

    def __getitem__(self, key):
        return self._environ[str(key).upper()]

    def __iter__(self):
        return iter(self._environ)

    def __len__(self):
        return len(self._environ)


class Resolver:
    def __init__(self, search_order):
        self._search_order = list(search_order)

    def append_source(self, source, *, name=None):
        """Append a semantic source without assigning behavior to its name."""
        self._search_order.append((name or type(source).__name__, source))

    def resolve(self, *args, default=_RAISE):
        last_exc = None
        for arg in args:
            if arg is None:
                continue

            expression = arg if isinstance(arg, Sigil) else str(arg)
            text = expression.original if isinstance(expression, Sigil) else expression

            try:
                return resolve_text(text, self._lookup)
            except KeyError as exc:
                last_exc = exc

        if default is not _RAISE:
            return default
        if last_exc is not None:
            raise last_exc
        raise KeyError("No arguments provided to resolve() or all were None")

    def find_value(self, key, fallback=None):
        """Return the first matching value from the configured semantic sources."""
        for _, source in self._search_order:
            try:
                return source[key]
            except (KeyError, IndexError, TypeError):
                continue
        return fallback

    def _lookup(self, key):
        value = self.find_value(key, _MISSING)
        if value is _MISSING:
            raise KeyError(key)
        return value

    def _resolve_key(self, key, fallback=None):
        key = key.strip()

        value = self.find_value(key, _MISSING)
        if value is not _MISSING:
            return value

        parts = re.split(r"[. ]+", key.replace("-", "_"))
        if len(parts) > 1:
            base = self.find_value(parts[0], _MISSING)
            if base is not _MISSING:
                try:
                    return follow_path(
                        base,
                        parts[1:],
                        lookup=self._lookup,
                        resolve_text=resolve_text,
                    )
                except KeyError:
                    pass

        return fallback

    def __getitem__(self, key):
        if isinstance(key, str) and key.startswith("[") and key.endswith("]"):
            key = key[1:-1]
        value = self._resolve_key(key, _MISSING)
        if value is _MISSING:
            raise KeyError(f"Cannot resolve key '{key}'")
        return value

    def __contains__(self, sigil_text):
        try:
            sigil = Sigil(sigil_text)
        except (ValueError, TypeError):
            return False

        try:
            sigil.resolve(self)
        except KeyError:
            return False
        return True

    def get(self, key, default=None):
        return self._resolve_key(key, fallback=default)

    def keys(self):
        return {
            key
            for _, source in self._search_order
            if isinstance(source, Mapping)
            for key in source
        }

    def __mod__(self, expression):
        if isinstance(expression, Sigil):
            return expression.resolve(self)
        return self.resolve(expression)
