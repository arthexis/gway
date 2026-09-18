"""Path traversal helpers for sigil resolution."""

def follow_path(value, parts, lookup=None, resolve_text=None):
    for part in parts:
        original_part = part
        if lookup and resolve_text and isinstance(part, str) and "[" in part and "]" in part:
            try:
                part = resolve_text(part, lookup)
            except KeyError:
                pass

        if isinstance(part, str):
            part = part.strip()
            if part.startswith("_"):
                raise KeyError(f"Path segment '{part}' not found")

        if isinstance(value, dict):
            if part in value:
                value = value[part]
                continue

            if isinstance(part, str):
                try:
                    numeric_part = int(part)
                except (ValueError, TypeError):
                    numeric_part = None

                if numeric_part is not None and numeric_part in value:
                    value = value[numeric_part]
                    continue

                normalized = part.lower().replace("-", "_")
                sentinel = object()
                resolved = sentinel
                for key, candidate in value.items():
                    if not isinstance(key, str):
                        continue
                    if key.lower().replace("-", "_") == normalized:
                        resolved = candidate
                        break
                if resolved is not sentinel:
                    value = resolved
                    continue

        idx = None
        if isinstance(part, int):
            idx = part
        elif isinstance(part, str):
            try:
                idx = int(part)
            except (ValueError, TypeError):
                idx = None

        if idx is not None and isinstance(value, (list, tuple)):
            value = value[idx]
            continue

        if isinstance(part, str) and hasattr(value, part):
            value = getattr(value, part)
            continue

        if hasattr(value, "__getitem__"):
            try:
                value = value[part]
                continue
            except Exception:
                pass

        raise KeyError(f"Path segment '{original_part}' not found")

    return value
