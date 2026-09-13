from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence

_GLOBAL_FLAGS = frozenset({"--json", "-i", "--interactive"})
_EXPLAIN_FLAGS = frozenset({"-e", "--explain"})
_RUNTIME_LIFECYCLE = frozenset({"install", "upgrade", "uninstall"})
_ORIGINAL_ARGV_ENV = "GWAY_RESUME_ORIGINAL_ARGV"


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


def _resume_error_args(args: Sequence[str]) -> list[str]:
    """Recover the user's original argv carried across process replacement."""
    encoded = os.environ.pop(_ORIGINAL_ARGV_ENV, None)
    if encoded is None:
        return list(args)
    try:
        decoded = json.loads(encoded)
    except json.JSONDecodeError:
        return list(args)
    if not isinstance(decoded, list) or not all(isinstance(arg, str) for arg in decoded):
        return list(args)
    return decoded


def _run_internal_resume(args: Sequence[str]) -> int | None:
    """Handle the process-replacement resume entry before ordinary CLI parsing."""
    if not args or args[0] != "--resume":
        return None
    error_args = _resume_error_args(args)
    if len(args) != 2:
        print("usage: python -m gway --resume CHECKPOINT", file=sys.stderr)
        print("gway: error: internal --resume requires exactly one checkpoint path", file=sys.stderr)
        return 2

    from .checkpoint import CheckpointError
    from .checkpoint_store import (
        claim_checkpoint,
        read_checkpoint,
        remove_checkpoint,
        restore_checkpoint,
    )
    from .cli import _handle_cli_exception, _render_result, _report_error
    from .explain import explain_scope, record, render_trace
    from .resume import resume_recipe
    from .runtime import GwayRuntime

    def handle_resume_error(exc: Exception) -> int:
        if isinstance(exc, CheckpointError):
            _report_error(exc, error_args)
            return 2
        return _handle_cli_exception(exc, error_args)

    def restore_claim(claimed_path: str, checkpoint_path: str) -> None:
        try:
            restore_checkpoint(claimed_path, checkpoint_path)
        except Exception as restore_exc:
            print(f"gway: additionally failed to restore checkpoint: {restore_exc}", file=sys.stderr)

    checkpoint_path = args[1]
    try:
        claimed_path = claim_checkpoint(checkpoint_path)
    except Exception as exc:
        return handle_resume_error(exc)

    try:
        checkpoint = read_checkpoint(claimed_path)
    except Exception as exc:
        restore_claim(str(claimed_path), checkpoint_path)
        return handle_resume_error(exc)
    except BaseException:
        restore_claim(str(claimed_path), checkpoint_path)
        raise

    with explain_scope(enabled=checkpoint.flags.explain) as trace:
        try:
            runtime = GwayRuntime()
            runtime.output_mode = checkpoint.flags.output_mode
            result = resume_recipe(checkpoint, runtime.dispatcher, runtime=runtime)
            remove_checkpoint(claimed_path)
            _render_result(
                result,
                json_output=checkpoint.flags.output_mode == "json",
            )
            return 0
        except Exception as exc:
            record(
                "execution.failure",
                "checkpoint resume failed",
                exception=type(exc).__name__,
                error=str(exc),
                checkpoint=checkpoint_path,
            )
            restore_claim(str(claimed_path), checkpoint_path)
            return handle_resume_error(exc)
        except BaseException:
            restore_claim(str(claimed_path), checkpoint_path)
            raise
        finally:
            if checkpoint.flags.explain:
                print(render_trace(trace), file=sys.stderr)


def _run_runtime_recipe(
    args: Sequence[str],
    *,
    error_args: Sequence[str] | None = None,
) -> int | None:
    global_flags, command_args = _partition_args(args)
    if not command_args or command_args[0] != "recipe":
        return None

    recipe_stage = command_args[1:]
    if "-" in recipe_stage:
        recipe_stage = recipe_stage[: recipe_stage.index("-")]
    if any(arg in {"-h", "--help"} for arg in recipe_stage):
        return None

    from .cli import _handle_cli_exception, _render_result
    from .runtime import GwayRuntime

    interactive = any(flag in {"-i", "--interactive"} for flag in global_flags)
    try:
        runtime = GwayRuntime()
        runtime.output_mode = "json" if "--json" in global_flags else None
        result = runtime.execute(command_args, interactive=interactive)
        _render_result(result, json_output="--json" in global_flags)
    except Exception as exc:
        return _handle_cli_exception(exc, list(error_args if error_args is not None else args))
    return 0


def _run_runtime_lifecycle(args: Sequence[str]) -> int | None:
    global_flags, command_args = _partition_args(args)
    if not command_args or command_args[0] not in _RUNTIME_LIFECYCLE:
        return None

    operation = command_args[0]
    option_args = command_args[1:]
    if "--" in option_args:
        option_args = option_args[: option_args.index("--")]
    help_requested = any(arg in {"-h", "--help"} for arg in option_args)

    if operation != "uninstall" and help_requested:
        return None

    if operation == "uninstall":
        if help_requested:
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
    detail = "--detail" in option_args
    on_progress = None
    if operation == "upgrade" and not json_output:
        on_progress = lambda result: _render_upgrade_result(result, detail=detail)

    try:
        result = GwayRuntime(on_progress=on_progress).execute(
            command_args,
            interactive=interactive,
        )
        if operation != "upgrade" or json_output:
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
    resume_result = _run_internal_resume(raw_args)
    if resume_result is not None:
        return resume_result

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

            recipe_result = _run_runtime_recipe(
                normalized or [],
                error_args=raw_args,
            )
            if recipe_result is not None:
                if recipe_result:
                    record(
                        "execution.failure",
                        "recipe command exited with non-zero status",
                        exit_code=recipe_result,
                    )
                return recipe_result

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
