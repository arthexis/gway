import re


class Sigil:
    """
    Represents a resolvable sigil in the format [key] or [key|fallback].
    Can be resolved using a callable finder passed at instantiation or via `%` operator.
    """

    _pattern = re.compile(r"\[([^\[\]|]*)(?:\|([^\[\]]*))?\]")

    def __init__(self, text):
        if not isinstance(text, str):
            raise TypeError("Sigil text must be a string")
        self.original = text

    def resolve(self, finder):
        """Resolve the sigil using the given finder callable."""

        def replacer(match):
            key = match.group(1).strip()
            fallback = match.group(2).strip() if match.group(2) is not None else None

            if match.group(2) is not None:
                if key == "":
                    raise ValueError("Empty key is not allowed in [|fallback]")
                if fallback == "":
                    raise ValueError(f"Empty fallback is not allowed in [{key}|]")
            elif key == "":
                raise ValueError("Empty key is not allowed in []")

            resolved = finder(key, fallback)
            return str(resolved) if resolved is not None else ""

        return re.sub(self._pattern, replacer, self.original) or None

    def __mod__(self, finder):
        """Allows use of `%` operator for resolution."""
        return self.resolve(finder)
    