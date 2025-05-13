import re
import os


class Sigil:
    """
    Represents a resolvable sigil in the format [key] or [key|fallback].
    Can be resolved using a callable finder passed at instantiation or via `%` operator.
    """

    _pattern = re.compile(r"\[([^\[\]|]*)(?:\|([^\[\]]*))?\]")

    def __init__(self, text):
        if not isinstance(text, str):
            raise TypeError("Sigil text must be a string")

        # Check for nested sigils
        if re.search(r"\[[^\[\]]*\[[^\[\]]*\]", text):
            raise ValueError("Nested sigils are not allowed")

        self.original = text

    def resolve(self, finder):
        """Resolve the sigil using the given finder callable or dictionary."""

        if isinstance(finder, dict):
            def _lookup(key, fallback):
                for variant in (key, key.lower(), key.upper()):
                    if variant in finder:
                        return finder[variant]
                return fallback
        elif callable(finder):
            def _lookup(key, fallback):
                for variant in (key, key.lower(), key.upper()):
                    val = finder(variant, None)
                    if val is not None:
                        return val
                return fallback
        else:
            raise TypeError("Finder must be a callable or a dictionary")

        def replacer(match):
            key = match.group(1).strip()
            fallback = match.group(2).strip() if match.group(2) is not None else None

            if key == "":
                raise ValueError("Empty key is not allowed")
            if match.group(2) is not None and fallback == "":
                raise ValueError(f"Empty fallback is not allowed in [{key}|]")

            resolved = _lookup(key, fallback)
            return str(resolved) if resolved is not None else ""

        return re.sub(self._pattern, replacer, self.original) or None

    def list_sigils(self):
        """Returns a list of all well-formed [sigils] in the original text (including brackets)."""
        return [match.group(0) for match in self._pattern.finditer(self.original)]

    def __mod__(self, finder):
        """Allows use of `%` operator for resolution."""
        return self.resolve(finder)


class Resolver:
    def __init__(self, search_order):
        """
        :param search_order: List of (name, source) pairs to search in order.
                             E.g., [('results', results), ('context', context), ('env', os.environ)]
        """
        self._search_order = search_order

    def append_source(self, source):
        self._search_order.append(source)

    def resolve(self, sigil):
        """Resolve [sigils] in a given string, using find_value()."""
        if not isinstance(sigil, str):
            return sigil
        if not isinstance(sigil, Sigil):
            sigil = Sigil(sigil)
        return sigil % self.find_value
    
    def find_value(self, key: str, fallback: str = None) -> str:
        """Find a value from the search sources provided in search_order."""
        for name, source in self._search_order:
            if name == "env":
                val = os.getenv(key.upper())
                if val is not None:
                    return val
            elif key in source:
                return source[key]
        return fallback

    def _resolve_key(self, key: str, fallback: str = None) -> str:
        """Tries find_value first, then attribute/dot-notation fallback."""
        val = self.find_value(key, fallback)
        if val is not None:
            return val

        # Dot notation traversal
        parts = key.replace('-', '_').split('.')
        current = self
        for part in parts:
            if hasattr(current, part):
                current = getattr(current, part)
            elif isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return None
        return current

    def __getitem__(self, key):
        value = self._resolve_key(key)
        if value is None:
            raise KeyError(f"Cannot resolve key '{key}'")
        return value

    def __contains__(self, sigil_text):
        try:
            sigil = Sigil(sigil_text)
        except (ValueError, TypeError):
            return False

        for raw in sigil.list_sigils():
            match = Sigil._pattern.match(raw)
            if not match:
                return False
            key = match.group(1).strip()
            fallback = match.group(2).strip() if match.group(2) is not None else None
            if self._resolve_key(key, fallback) is None:
                return False
        return True
