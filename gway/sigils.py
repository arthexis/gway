# file: gway/sigils.py

import re
import os
import json

class Sigil:
    """Represent a ``[sigil]`` placeholder or plain text."""

    _pattern = re.compile(r"\[([^\[\]]+)\]")

    def __init__(self, text):
        self.original = text or ''

    @property
    def is_eager(self) -> bool:
        """Return ``True`` when the sigil text begins with ``%``."""
        return isinstance(self.original, str) and self.original.startswith('%')

    @property
    def text(self) -> str:
        """The sigil string without the ``%`` prefix."""
        return self.original[1:] if self.is_eager else self.original

    def _make_lookup(self, finder):
        def lookup(key):
            # Try all dash/underscore/case variants
            variants = {
                key, key.replace('-', '_'), key.replace('_', '-'),
                key.lower(), key.upper()
            }
            for variant in variants:
                val = None
                if isinstance(finder, dict):
                    val = finder.get(variant)
                elif callable(finder):
                    try:
                        val = finder(variant, None, True)
                    except TypeError:
                        val = finder(variant, None)
                if val is not None:
                    return val
            return None
        return lookup

    def resolve(self, finder):
        return _replace_sigils(self.text, self._make_lookup(finder))

    def list_sigils(self):
        return [match.group(0) for match in self._pattern.finditer(self.text)]

    def __mod__(self, finder):
        return self.resolve(finder)

    def __str__(self):
        return str(self.original)

    def __repr__(self):
        return f"Sigil({self.original!r})"


def _unquote(val):
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    return val

def _resolve_single(raw, lookup_fn):
    """Resolve a single sigil value and return it without string conversion."""
    from gway import gw

    raw = raw.strip()
    quoted = (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'"))
    key = _unquote(raw) if quoted else raw
    key = re.sub(r"^(gw|gway)[. ]+", "", key)

    val = lookup_fn(key)
    if val is None:
        parts = re.split(r"[. ]+", key)
        if len(parts) > 1:
            base = lookup_fn(parts[0])
            if base is not None:
                try:
                    val = _follow_path(base, parts[1:])
                except KeyError:
                    val = None

    if val is not None:
        gw.verbose(f"Resolved sigil [{raw}] → {val}")
        return val

    if quoted:
        gw.verbose(f"Sigil [{raw}] not resolved, using quoted literal '{key}'")
        return key

    raise KeyError(f"Unresolved sigil: [{raw}]")

def _follow_path(value, parts):
    for part in parts:
        if part.startswith('_'):
            raise KeyError(f"Path segment '{part}' not found")
        if isinstance(value, dict) and part in value:
            value = value[part]
            continue
        try:
            idx = int(part)
            if isinstance(value, (list, tuple)):
                value = value[idx]
                continue
        except (ValueError, TypeError):
            pass
        if hasattr(value, part):
            value = getattr(value, part)
            continue
        if hasattr(value, '__getitem__'):
            try:
                value = value[part]
                continue
            except Exception:
                pass
        raise KeyError(f"Path segment '{part}' not found")
    return value

def _replace_sigils(text, lookup_fn):
    """
    Replace all sigils in the text, raising if any sigil is unresolved.
    """

    matches = list(Sigil._pattern.finditer(text))
    if len(matches) == 1 and matches[0].span() == (0, len(text)):
        return _resolve_single(matches[0].group(1), lookup_fn)

    def replacer(match):
        val = _resolve_single(match.group(1), lookup_fn)
        if isinstance(val, str):
            return val
        return json.dumps(val, default=str)

    return re.sub(Sigil._pattern, replacer, text)

class Resolver:
    def __init__(self, search_order):
        """
        :param search_order: List of (name, source) pairs to search in order.
        """
        self._search_order = search_order

    def append_source(self, source):
        self._search_order.append(source)

    def resolve(self, *args, default="_raise"):
        """
        Attempt to resolve sigils each argument in order (ignoring None/False). Return the first successful result.
        If none resolve, return the 'default' parameter unresolved (if provided), otherwise raise KeyError.
        """
        from gway import gw

        last_exc = None
        for arg in args:
            # Discard None or False values (but NOT 0 or '')
            if arg is None:
                continue
            arg = '' if not arg else arg
            try:
                sigil = arg if isinstance(arg, Sigil) else Sigil(str(arg))
                lookup = lambda key: self.find_value(key, None, exec=True)
                result = _replace_sigils(sigil.original, lookup)
                return result
            except KeyError as e:
                gw.verbose(f"Could not resolve sigil(s) in '{arg}': {e}")
                last_exc = e
        # return provided default unless user passed the '_raise' sentinel
        if default != '_raise':
            return default
        if last_exc is not None:
            gw.error(f"All sigil resolutions failed: {last_exc}")
            raise last_exc
        gw.error("No arguments provided to resolve() or all were None/False")
        raise KeyError("No arguments provided to resolve() or all were None/False")

    def find_value(self, key: str, fallback: str = None, exec: bool = False) -> str:
        for name, source in self._search_order:
            if name == "env":
                val = os.getenv(key.upper())
                if val is not None:
                    return val
            elif isinstance(source, dict) and key in source:
                return source[key]
            elif hasattr(source, "__getitem__"):
                try:
                    val = source[key]
                    if val is not None:
                        return val
                except Exception:
                    pass

        if exec:
            args = []
            kwargs = {}
            func_name = key
            tokens = []
            if ":" in key:
                parts = key.split(":")
                func_name, tokens = parts[0], parts[1:]
            elif "=" in key:
                func_name, param = key.split("=", 1)
                tokens = [param]
            for tok in tokens:
                if "=" in tok:
                    k, v = tok.split("=", 1)
                    kwargs[k] = v
                else:
                    args.append(tok)

            variants = {
                func_name,
                func_name.replace('-', '_'),
                func_name.replace('_', '-'),
                func_name.lower(),
                func_name.upper(),
            }
            for variant in variants:
                obj = self
                try:
                    for part in variant.split('.'):
                        obj = getattr(obj, part)
                    if callable(obj):
                        return obj(*args, **kwargs)
                except Exception:
                    continue

        return fallback

    def _resolve_key(self, key: str, fallback: str = None) -> str:
        key = key.strip()
        key = re.sub(r"^(gw|gway)[. ]+", "", key)

        val = self.find_value(key, None)
        if val is not None:
            return val

        parts = re.split(r"[. ]+", key.replace('-', '_'))
        if len(parts) > 1:
            base = self.find_value(parts[0], None)
            if base is not None:
                try:
                    return _follow_path(base, parts[1:])
                except KeyError:
                    return fallback

        parts = re.split(r"[. ]+", key.replace('-', '_'))
        current = self
        for part in parts:
            if part.startswith('_'):
                return fallback
            if hasattr(current, part):
                current = getattr(current, part)
            elif isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return fallback
        return current

    def __getitem__(self, key):
        if isinstance(key, str):
            if key.startswith('%[') and key.endswith(']'):
                key = key[2:-1]
            elif key.startswith('[') and key.endswith(']'):
                key = key[1:-1]
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
            if self._resolve_key(key, None) is None:
                return False
        return True

    def get(self, key, default=None):
        return self._resolve_key(key, fallback=default)

    def keys(self):
        return {key for _, source in self._search_order if isinstance(source, dict) for key in source}

class Spool:
    """
    A spool is a collection of sigils.
    Represents a list of Sigils, and supports batch resolution.
    Example: Spool('[HOST]', '[HOSTNAME]', sigiled_var, '127.0.0.1')
    or __('[HOST]', '[HOSTNAME]', sigiled_var, '127.0.0.1')
    All elements are converted to Sigil if not already.
    """
    def __init__(self, *values):
        self.sigils = []
        for item in values:
            if not item: continue
            self._add_flat(item)

    @property
    def is_eager(self) -> bool:
        return any(getattr(s, 'is_eager', False) for s in self.sigils)

    def _add_flat(self, item):
        # Recursively flatten
        if isinstance(item, (list, tuple, set)):
            for sub in item:
                self._add_flat(sub)
        else:
            self.sigils.append(self._to_sigil(item))

    @staticmethod
    def _to_sigil(value):
        if isinstance(value, Sigil):
            return value
        return Sigil(str(value))

    def resolve(self, resolver=None):
        if resolver is None:
            from gway import gw
            resolver = gw
        last_exc = None
        for sigil in self:
            try:
                result = sigil.resolve(resolver)
                return result
            except Exception as e:
                last_exc = e
        if last_exc:
            if hasattr(resolver, "error"):
                resolver.error(f"Spool: All resolutions failed: {last_exc}")
            raise last_exc
        raise KeyError("Spool: No items to resolve.")

    # --- Sequence protocol ---
    def __getitem__(self, idx):
        return self.sigils[idx]
    def __len__(self):
        return len(self.sigils)
    def __iter__(self):
        return iter(self.sigils)
    def append(self, value):
        self._add_flat(value)
    def extend(self, values):
        self._add_flat(values)
    def index(self, value):
        return self.sigils.index(self._to_sigil(value))
    def count(self, value):
        return self.sigils.count(self._to_sigil(value))

    def __repr__(self):
        return f"Spool({', '.join(repr(s) for s in self.sigils)})"
    def __str__(self):
        return " | ".join(str(s) for s in self.sigils)

__ = Spool
