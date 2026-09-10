from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Callable

from .chain_context import chain_context_scope, publish_chain_result
from .dispatcher.errors import CommandNotFound, DispatchError
from .expression import MANAGED_EXPRESSION_PROJECT, normalize_managed_args
from .solve import solve_values
from .stage import Stage, StageKind, parse_stages

if TYPE_CHECKING:
    from .dispatcher import Dispatcher


def _transfer_values(result: object) -> list[object]:
    """Normalize one stage result into the next stage's implicit positionals."""
    if result is None or isinstance(result, Mapping):
        return []
    if isinstance(result, Sequence) and not isinstance(result, (str, bytes, bytearray)):
        return list(result)
    return [result]


def _render_transfer(values: Sequence[object]) -> list[str]:
    """Render transferred values into ordinary CLI positional tokens."""
    return [value.decode() if isinstance(value, bytes) else str(value) for value in values]


def _run_command_stage(
    dispatcher: Dispatcher,
    stage: Stage,
    transfer: Sequence[object],
    *,
    interactive: bool,
) -> object:
    """Run one managed command stage with implicit positionals inserted after its path."""
    project_name, project_args = normalize_managed_args(stage.tokens)
    rendered = _render_transfer(transfer)

    if project_name == MANAGED_EXPRESSION_PROJECT:
        if rendered:
            raise DispatchError("fallback expressions cannot receive implicit chain positionals")
        return dispatcher.run(project_name, project_args, interactive=interactive)

    project = dispatcher.registry.require(project_name)
    commands = dispatcher.commands(project_name)
    try:
        command, argv = dispatcher._resolve_command(commands, project_args)
    except CommandNotFound:
        if not project.default_command:
            raise
        command, argv = dispatcher._resolve_default_command(
            commands,
            project.default_command,
            project_args,
        )

    return dispatcher.run(
        project_name,
        [*command.path, *rendered, *argv],
        interactive=interactive,
    )


def run_chain(
    dispatcher: Dispatcher,
    tokens: Sequence[str],
    *,
    interactive: bool = False,
    prompt: Callable[[str], str] | None = None,
) -> object:
    """Execute parsed stages left-to-right with classic implicit result transfer."""
    stages = parse_stages(tokens)
    result: object = None

    if interactive and prompt is None:
        from .cli import _prompt_required_value

        prompt = _prompt_required_value

    with chain_context_scope():
        for index, stage in enumerate(stages):
            transfer = [] if index == 0 else _transfer_values(result)
            if stage.kind is StageKind.SOLVE:
                values = [*_render_transfer(transfer), *stage.raw_tokens]
                result = solve_values(
                    values,
                    interactive=interactive,
                    prompt=prompt,
                    paths=dispatcher.registry.paths,
                )
            else:
                result = _run_command_stage(
                    dispatcher,
                    stage,
                    transfer,
                    interactive=interactive,
                )
            publish_chain_result(result)

    return result


__all__ = ["run_chain"]
