"""Context-free sigil values."""

from collections.abc import Mapping
import re

from .resolution import is_single_sigil, resolve_text, split_outside_brackets_once

_PATTERN = re.compile(r"\[([^\[\]]+)\]")
_MISSING = object()


def _lookup_for(context):
    def lookup(key):
        variants = (
            key,
            key.replace("-", "_"),
            key.replace("_", "-"),
            key.lower(),
            key.upper(),
        )
        for variant in variants:
            if isinstance(context, Mapping):
                if variant in context:
                    return context[variant]
                continue
            if hasattr(context, "find_value"):
                value = context.find_value(variant, _MISSING)
                if value is not _MISSING:
                    return value
                continue
            if callable(context):
                try:
                    return context(variant)
                except KeyError:
                    continue
        raise KeyError(key)

    return lookup


class Sigil:
    """A context-free sigil expression with implicit outer brackets."""

    _pattern = _PATTERN

    def __init__(self, text):
        text = "" if text is None else str(text)
        self.original = text if is_single_sigil(text) else f"[{text}]"

    @property
    def text(self):
        return self.original[1:-1]

    @property
    def primary(self):
        """Return the expression before an inline fallback, if present."""
        split = split_outside_brackets_once(self.text, "|")
        return (split[0] if split else self.text).strip()

    @property
    def fallback(self):
        """Return the literal inline fallback, or None when none is declared."""
        split = split_outside_brackets_once(self.text, "|")
        if split is None:
            return None
        value = split[1].strip()
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            return value[1:-1]
        return value

    def resolve_primary(self, context):
        """Resolve only the primary expression, ignoring an inline fallback."""
        return Sigil(self.primary).resolve(context)

    def resolve(self, context):
        resolver = getattr(context, "resolve", None)
        if callable(resolver):
            return resolver(self.original)
        return resolve_text(self.original, _lookup_for(context))

    def list_sigils(self):
        return [match.group(0) for match in self._pattern.finditer(self.original)]

    def __mod__(self, context):
        return self.resolve(context)

    def __rmod__(self, context):
        return self.resolve(context)

    def __str__(self):
        return self.original

    def __repr__(self):
        return f"Sigil({self.text!r})"
