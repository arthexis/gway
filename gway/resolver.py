"""Resolver policy and source precedence."""

import os
import re

from .sigil import Sigil
from .sigil_paths import follow_path
from .sigil_resolution import resolve_text


class Resolver:
    def __init__(self, search_order):
        self._search_order = search_order

    def append_source(self, source):
        self._search_order.append(source)

    def resolve(self, *args, default="_raise"):
        last_exc = None
        for arg in args:
            if arg is None:
                continue

            expression = arg if isinstance(arg, Sigil) else str(arg)
            text = expression.original if isinstance(expression, Sigil) else expression

            try:
                return resolve_text(
                    text,
                    lambda key: self.find_value(key, None),
                )
            except KeyError as exc:
                last_exc = exc

        if default != "_raise":
            return default
        if last_exc is not None:
            raise last_exc
        raise KeyError("No arguments provided to resolve() or all were None")

    def find_value(self, key, fallback=None, exec=False):
        for name, source in self._search_order:
            if name == "env":
                value = os.getenv(key.upper())
                if value is not None:
                    return value
            elif isinstance(source, dict) and key in source:
                return source[key]
            elif hasattr(source, "__getitem__"):
                try:
                    value = source[key]
                    if value is not None:
                        return value
                except Exception:
                    pass

        if exec:
            value = self._resolve_callable_legacy(key)
            if value is not None:
                return value

        return fallback

    def _resolve_callable_legacy(self, key):
        func_name = key.strip()
        variants = (
            func_name,
            func_name.replace("-", "_"),
            func_name.replace("_", "-"),
            func_name.lower(),
            func_name.upper(),
        )
        for variant in variants:
            obj = self
            try:
                for part in variant.split("."):
                    obj = getattr(obj, part)
            except Exception:
                continue
            if callable(obj):
                try:
                    return obj()
                except TypeError:
                    continue
        return None

    def _resolve_key(self, key, fallback=None):
        key = key.strip()
        key = re.sub(r"^(gw|gway)[. ]+", "", key)

        value = self.find_value(key, None)
        if value is not None:
            return value

        parts = re.split(r"[. ]+", key.replace("-", "_"))
        if len(parts) > 1:
            base = self.find_value(parts[0], None)
            if base is not None:
                try:
                    return follow_path(
                        base,
                        parts[1:],
                        lookup=lambda inner: self.find_value(inner, None),
                        resolve_text=resolve_text,
                    )
                except KeyError:
                    return fallback

        current = self
        for part in parts:
            if part.startswith("_"):
                return fallback
            if hasattr(current, part):
                current = getattr(current, part)
            elif isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return fallback
        return current

    def __getitem__(self, key):
        if isinstance(key, str) and key.startswith("[") and key.endswith("]"):
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
            if isinstance(source, dict)
            for key in source
        }

    def __mod__(self, expression):
        if isinstance(expression, Sigil):
            return expression.resolve(self)
        return self.resolve(expression)
