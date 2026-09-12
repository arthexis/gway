from __future__ import annotations

import os
import sys
from collections.abc import Sequence

_GLOBAL_FLAGS = frozenset({"--json", "-i", "--interactive"})
_EXPLAIN_FLAGS = frozenset({"-e", "--explain"})


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


def _run_uninstall(args: Sequence[str]) -> int | None:
    global_flags, command_args = _partition_args(args)
    if not command_args or command_args[0] != "uninstall":
        return None

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

    from .cli import _handle_cli_exception, _managed_status, _render_result
    from .install import Installer
    from .registry import Registry

    try:
        project = Installer(Registry()).uninstall(command_args[1])
        result = _managed_status("uninstalled", project)
        _render_result(result, json_output="--json" in global_flags)
    except Exception as exc:
        return _handle_cli_exception(exc, list(args))
    return 0


def _run_recipe(args: Sequence[str]) -> int | None:
    global_flags, command_args = _partition_args(args)
    if not command_args or command_args[0] != "recipe":
        return None

    if command_args in (["recipe", "-h"], ["recipe", "--help"]):
        print("usage: gway recipe [-h] [-i] FILE.rx")
        print()
        print("Execute a GWAY recipe file with shared named context between statements.")
        print("  -i, --interactive  prompt for missing required values")
        return 0

    if len(command_args) != 2 or command_args[1] == "--":
        print("usage: gway recipe [-h] [-i] FILE.rx", file=sys.stderr)
        print(
            "gway recipe: error: the following arguments are required: FILE.rx"
            if len(command_args) == 1
            else "gway recipe: error: expected exactly one recipe file",
            file=sys.stderr,
        )
        return 2

    from .cli import _handle_cli_exception, _render_result
    from .dispatcher import Dispatcher
    from .recipe import RecipeError, run_recipe

    try:
        run_recipe(
            command_args[1],
            Dispatcher(),
            interactive=any(flag in {"-i", "--interactive"} for flag in global_flags),
            on_result=lambda result: _render_result(
                result,
                json_output="--json" in global_flags,
            ),
        )
    except RecipeError as exc:
        print(f"gway: {exc}", file=sys.stderr)
        return 2
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
            uninstall_result = _run_uninstall(args)
            if uninstall_result is not None:
                if uninstall_result:
                    record(
                        "execution.failure",
                        "command exited during uninstall",
                        exit_code=uninstall_result,
                    )
                return uninstall_result

            recipe_result = _run_recipe(args)
            if recipe_result is not None:
                if recipe_result:
                    record(
                        "execution.failure",
                        "command exited during recipe execution",
                        exit_code=recipe_result,
                    )
                return recipe_result

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
