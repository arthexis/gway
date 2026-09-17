from __future__ import annotations

import json
import math
import os
import sys
from collections.abc import Mapping, Sequence

_RESET = "\033[0m"
_KEY = "\033[36m"
_STRING = "\033[32m"
_NUMBER = "\033[33m"
_BOOL = "\033[35m"
_NULL = "\033[2m"


def _paint(text: str, code: str, *, color: bool) -> str:
    if not color:
        return text
    return f"{code}{text}{_RESET}"


def _scalar_text(value: object, *, color: bool) -> str:
    if value is None:
        return _paint("null", _NULL, color=color)
    if isinstance(value, bool):
        return _paint("true" if value else "false", _BOOL, color=color)
    if isinstance(value, (int, float)):
        return _paint(str(value), _NUMBER, color=color)
    if isinstance(value, str):
        return _paint(value, _STRING, color=color)
    return str(value)


def _is_nested(value: object) -> bool:
    return isinstance(value, Mapping) or (
        isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray))
    )


def _empty_collection_text(value: object) -> str | None:
    if isinstance(value, Mapping) and not value:
        return "{}"
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) and not value:
        return "[]"
    return None


def _pretty_lines(value: object, *, indent: int = 0, color: bool = False) -> list[str]:
    prefix = "  " * indent
    empty = _empty_collection_text(value)
    if empty is not None:
        return [f"{prefix}{empty}"]

    if isinstance(value, Mapping):
        lines: list[str] = []
        for key, item in value.items():
            label = _paint(str(key), _KEY, color=color)
            item_empty = _empty_collection_text(item)
            if item_empty is not None:
                lines.append(f"{prefix}{label}: {item_empty}")
            elif _is_nested(item):
                lines.append(f"{prefix}{label}:")
                lines.extend(_pretty_lines(item, indent=indent + 1, color=color))
            else:
                lines.append(f"{prefix}{label}: {_scalar_text(item, color=color)}")
        return lines

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        lines = []
        for item in value:
            item_empty = _empty_collection_text(item)
            if item_empty is not None:
                lines.append(f"{prefix}- {item_empty}")
            elif _is_nested(item):
                lines.append(f"{prefix}-")
                lines.extend(_pretty_lines(item, indent=indent + 1, color=color))
            else:
                lines.append(f"{prefix}- {_scalar_text(item, color=color)}")
        return lines

    return [f"{prefix}{_scalar_text(value, color=color)}"]


def _json_safe(value: object) -> object:
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_safe(item) for item in value]
    return value


def _json_result(result: object, *, result_name: str | None) -> object:
    safe_result = _json_safe(result)
    if isinstance(result, Mapping) or (
        isinstance(result, Sequence) and not isinstance(result, (str, bytes, bytearray))
    ):
        return safe_result
    return {result_name or "result": safe_result}


def _color_enabled() -> bool:
    if "NO_COLOR" in os.environ or os.environ.get("TERM") == "dumb":
        return False
    return bool(getattr(sys.stdout, "isatty", lambda: False)())


def _render_result(
    result: object,
    *,
    json_output: bool = False,
    color: bool | None = None,
    result_name: str | None = None,
) -> None:
    if result is None and not json_output:
        return
    if json_output:
        print(
            json.dumps(
                _json_result(result, result_name=result_name),
                indent=2,
                default=str,
                allow_nan=False,
            )
        )
        return

    use_color = _color_enabled() if color is None else color
    for line in _pretty_lines(result, color=use_color):
        print(line)


def _render_upgrade_record(record: dict[str, object], *, detail: bool) -> None:
    if detail:
        _render_result(record)
        return
    revision = record.get("revision")
    suffix = f" {str(revision)[:12]}" if revision else ""
    print(f"{record['status']} {record['name']}{suffix}")
