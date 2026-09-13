from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence

_GLOBAL_FLAGS = frozenset({"--json", "-i", "--interactive"})
_EXPLAIN_FLAGS = frozenset({"-e", "--explain"})
_RUNTIME_LIFECYCLE = frozenset({"install", "upgrade", "uninstall"})


def _partition_args(args: Sequence[str]) -> tuple[list[str], list[str]]:
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
    return global_flags, command_args


def _normalize_install_args(argv: Sequence[str] | None) -> tuple[list[str] | None, int | None]:
    if argv is None:
        args = list(sys.argv[1:])
    else:
        args = list(argv)

    global_flags, command_args = _partition_args(args)

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


def _render_upgrade_result(result: object, *, detail: bool) -> None:
    from .cli import _render_upgrade_record, _render_result

    if isinstance(result, Mapping):
        _render_upgrade_record(dict(result), detail=detail)
        return
    if isinstance(result, Sequence) and not isinstance(result, (str, bytes, bytearray)):
        for record in result:
            if isinstance(record, Mapping):
                _render_upgrade_record(dict(record), detail=detail)
            else:
                _render_result(record)
        return
    _render_result(result)


def _run_runtime_lifecycle(args: Sequence[str]) -> int | None:
    global_flags, command_args = _partition_args(args)
    if not command_args or command_args[0] not in _RUNTIME_LIFECYCLE:
        return None

    operation = command_args[0]
    if operation != "uninstall" and any(arg in {"-h", "--help"} for arg in command_args[1:]):
        return None

    if operation == "uninstall":
        if command_args in (["uninstall", "-h"], ["uninstall", "--help"]):
            print("usage: gway uninstall [-h] project")
            print()
            print("Uninstall a registered project and its GWAY-managed artifacts.")
            return 0
        if len(command_args) != 2 or command_args[1] == "--":
            print("usage: gway uninstall [-h] project", file=sys.stderr)
            print(
                "gway uninstall: error: the following arguments are required: project"
                if len(command_args) == 1
                else "gway uninstall: error: expected exactly one project",
                file=sys.stderr,
            )
            return 2

    from .cli import _handle_cli_exception, _render_result
    from .runtime import GwayRuntime

    interactive = any(flag in {"-i", "--interactive"} for flag in global_flags)
    json_output = "--json" in global_flags
    try:
        result = GwayRuntime().execute(command_args, interactive=interactive)
        if operation == "upgrade" and not json_output:
            _render_upgrade_result(result, detail="--detail" in command_args)
        else:
            _render_result(result, json_output=json_output)
    except Exception as exc:
        return _handle_cli_exception(exc, list(args))
    return 0


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

            lifecycle_result = _run_runtime_lifecycle(normalized or [])
            if lifecycle_result is not None:
                if lifecycle_result:
                    record(
                        "execution.failure",
                        "lifecycle command exited with non-zero status",
                        exit_code=lifecycle_result,
                    )
                return lifecycle_result

            from .cli import main as cli_main

            result = cli_main(normalized)
            if result:
                record(
                    "execution.failure",
                    "command exited with non-zero status",
                    exit_code=result,
                )
            return result
        except SystemExit:
            raise
        except BaseException as exc:
            record(
                "execution.failure",
                "command raised an exception",
                exception=type(exc).__name__,
                error=str(exc),
            )
            raise
        finally:
            if explain:
                print(render_trace(trace), file=sys.stderr)
