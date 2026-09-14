from __future__ import annotations

import argparse
from collections.abc import Sequence

from .logging import configure, current_context


def run_log(argv: Sequence[str]) -> dict[str, object]:
    """Inspect or update the logging context for the current GWAY run."""
    parser = argparse.ArgumentParser(prog="gway log", add_help=False)
    parser.add_argument("--tags", action="append", default=[])
    parser.add_argument("--to", action="append", default=[])
    namespace, unknown = parser.parse_known_args(list(argv))
    if unknown:
        raise ValueError(f"unrecognized log arguments: {' '.join(unknown)}")

    tags = tuple(
        tag.strip()
        for value in namespace.tags
        for tag in value.split(",")
        if tag.strip()
    )
    destinations = tuple(value.strip() for value in namespace.to if value.strip())
    if tags or destinations:
        return configure(tags=tags, to=destinations)
    return current_context()


__all__ = ["run_log"]
