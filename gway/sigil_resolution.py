"""Pure sigil expression resolution helpers."""

import json
import re

from .sigil_paths import follow_path

_PATTERN = re.compile(r"\[([^\[\]]+)\]")


def is_single_sigil(text):
    if not isinstance(text, str) or not text or text[0] != "[" or text[-1] != "]":
        return False

    depth = 0
    for index, char in enumerate(text):
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth < 0:
                return False
            if depth == 0 and index != len(text) - 1:
                return False
    return depth == 0


def split_outside_brackets_once(text, delimiter):
    depth = 0
    for index, char in enumerate(text):
        if char == "[":
            depth += 1
        elif char == "]":
            if depth > 0:
                depth -= 1
        elif char == delimiter and depth == 0:
            return text[:index], text[index + 1 :]
    return None


def _unquote(value):
    if (
        value.startswith('"') and value.endswith('"')
    ) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


def resolve_single(raw, lookup):
    raw = raw.strip()
    original_raw = raw
    quoted = (
        raw.startswith('"') and raw.endswith('"')
    ) or (
        raw.startswith("'") and raw.endswith("'")
    )

    fallback_spec = None
    fallback_quoted = False
    if not quoted:
        fallback_split = split_outside_brackets_once(raw, "|")
        if fallback_split:
            raw, fallback_spec = fallback_split
            raw = raw.strip()
            fallback_spec = fallback_spec.strip()
            fallback_quoted = (
                fallback_spec.startswith('"') and fallback_spec.endswith('"')
            ) or (
                fallback_spec.startswith("'") and fallback_spec.endswith("'")
            )

    key = _unquote(raw) if quoted else raw
    key = re.sub(r"^(gw|gway)[. ]+", "", key)

    if not quoted and "[" in key and "]" in key:
        nested = resolve_text(key, lookup)
        if not isinstance(nested, str):
            return nested
        key = nested

    value = lookup(key)
    if value is None:
        parts = re.split(r"[. ]+", key)
        if len(parts) > 1:
            base = lookup(parts[0])
            if base is not None:
                try:
                    value = follow_path(
                        base,
                        parts[1:],
                        lookup=lookup,
                        resolve_text=resolve_text,
                    )
                except KeyError:
                    value = None

    if value is not None:
        return value

    if fallback_spec is not None:
        fallback_source = _unquote(fallback_spec) if fallback_quoted else fallback_spec
        if not fallback_source:
            return ""
        try:
            return resolve_text(fallback_source, lookup)
        except KeyError:
            return fallback_source

    raise KeyError(f"Unresolved sigil: [{original_raw}]")


def resolve_text(text, lookup):
    if is_single_sigil(text):
        return resolve_single(text[1:-1], lookup)

    matches = list(_PATTERN.finditer(text))
    if len(matches) == 1 and matches[0].span() == (0, len(text)):
        return resolve_single(matches[0].group(1), lookup)

    def replacer(match):
        value = resolve_single(match.group(1), lookup)
        if isinstance(value, str):
            return value
        return json.dumps(value, default=str)

    return _PATTERN.sub(replacer, text)
