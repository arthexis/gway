from __future__ import annotations

import os
import sys
from collections.abc import Sequence

_GLOBAL_FLAGS = frozenset({"--json", "-i", "--interactive"})
_EXPLAIN_FLAGS = frozenset({"-e", "--explain"})


def _normalize_install_args(argv: Sequence[str] | None) -> tuple[list[str] | None, int | None]:
    if argv is None:
        args = list(sys.argv[1:])
    else:
        args = list(argv)

    global_flags: list[str] = []
    command_args: list[str] = []
    literal = False
    for arg in args:
        if not literal and arg == "--":
            literal = True
            command_args.append(arg)
        elif not literal and arg in _GLOBAL_FLAGS:
            global_flags.append(arg)
        else:
            command_args.append(arg)

    if command_args == ["install"]:
        print("usage: gway install [-h] [--service] [--self] [project]", file=sys.stderr)
        print(
            "gway install: error: the following arguments are required: project",
            file=sys.stderr,
        )
        print(
            "hint: use 'gway install --self' or 'gway install gway' to install GWAY itself",
            file=sys.stderr,
        )
        return None, 2

    if command_args in (["install", "--self"], ["install", "gway"]):
        return [*global_flags, "upgrade", "gway"], None

    return args, None


def _extract_explain_flag(argv: Sequence[str]) -> tuple[list[str], bool]:
    filtered: list[str] = []
    explain = False
    literal = False

    for arg in argv:
        if literal:
            filtered.append(arg)
            continue
        if arg == "--":
            literal = True
            filtered.append(arg)
            continue
        if arg in _EXPLAIN_FLAGS:
            explain = True
            continue
        filtered.append(arg)

    return filtered, explain


def main(argv: Sequence[str] | None = None) -> int:
    """Run the GWAY CLI with a noninteractive Git environment."""
    os.environ["GIT_TERMINAL_PROMPT"] = "0"

    raw_args = list(sys.argv[1:] if argv is None else argv)
    args, explain = _extract_explain_flag(raw_args)

    from .explain import explain_scope, record, render_trace

    with explain_scope(enabled=explain) as trace:
        try:
            normalized, early_result = _normalize_install_args(args)
            if early_result is not None:
                if early_result:
                    record(
                        "execution.failure",
                        "command exited before dispatch",
                        exit_code=early_result,
                    )
                return early_result

            from .cli import main as cli_main

            result = cli_main(normalized)
            if result:
                record(
                    "execution.failure",
                    "command exited with non-zero status",
                    exit_code=result,
                )
            return result
        except BaseException as exc:
            record(
                "execution.failure",
                "command raised an exception",
                exception=type(exc).__name__,
                message=str(exc),
            )
            raise
        finally:
            if explain:
                print(render_trace(trace), file=sys.stderr)
