from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from typing import TYPE_CHECKING

from .chain_context import chain_context_scope, publish_chain_result
from .dispatcher.errors import CommandNotFound, DispatchError
from .expression import MANAGED_EXPRESSION_PROJECT, normalize_managed_args
from .solve import solve_values
from .stage import Stage, StageKind, parse_stages
from .transfer import encode_transfer, transfer_scope

if TYPE_CHECKING:
    from .dispatcher import Dispatcher

_SELECTOR = re.compile(r"\[(?P<index>[1-9]\d*)\]\Z")
_WILDCARD = "[*]"


def _transfer_values(result: object) -> list[object]:
    """Normalize one stage result into the next stage's positional transfer values."""
    if result is None or isinstance(result, Mapping):
        return []
    if isinstance(result, Sequence) and not isinstance(result, (str, bytes, bytearray)):
        return list(result)
    return [result]


def _selector_index(token: str) -> int | None:
    """Return the 1-based transfer index selected by an exact numeric selector."""
    match = _SELECTOR.fullmatch(token)
    return int(match.group("index")) if match is not None else None


def _route_transfer(argv: Sequence[str], transfer: Sequence[object]) -> list[str | object]:
    """Materialize explicit selectors or apply the implicit leading wildcard rule."""
    numeric = [_selector_index(token) for token in argv]
    explicit = any(index is not None for index in numeric) or _WILDCARD in argv
    if not explicit:
        return [*transfer, *argv]

    if argv.count(_WILDCARD) > 1:
        raise DispatchError("a chain stage may contain at most one [*] selector")

    selected = {index for index in numeric if index is not None}
    if selected and max(selected) > len(transfer):
        missing = max(selected)
        raise DispatchError(
            f"chain transfer selector [{missing}] is out of range for {len(transfer)} value(s)"
        )

    remainder = [
        value
        for index, value in enumerate(transfer, start=1)
        if index not in selected
    ]
    routed: list[str | object] = []
    for token, index in zip(argv, numeric, strict=True):
        if index is not None:
            routed.append(transfer[index - 1])
        elif token == _WILDCARD:
            routed.extend(remainder)
        else:
            routed.append(token)
    return routed


def _encode_routed_values(values: Sequence[str | object], original_argv: Sequence[str]) -> list[str]:
    """Encode transferred objects opaquely while leaving original CLI tokens untouched."""
    original_ids: dict[int, int] = {}
    for token in original_argv:
        original_ids[id(token)] = original_ids.get(id(token), 0) + 1

    encoded: list[str] = []
    for value in values:
        if isinstance(value, str) and original_ids.get(id(value), 0):
            original_ids[id(value)] -= 1
            encoded.append(value)
        else:
            encoded.append(encode_transfer(value))
    return encoded


def _literal_solve_transfer(value: object) -> str:
    """Render transferred data literally when it is consumed by a solve/template stage."""
    if isinstance(value, bytes):
        text = value.decode(errors="replace")
    elif isinstance(value, bytearray):
        text = bytes(value).decode(errors="replace")
    else:
        text = str(value)
    return text.replace("[", "[[").replace("]", "]] ").replace("]] ", "]]")


def _run_command_stage(
    dispatcher: Dispatcher,
    stage: Stage,
    transfer: Sequence[object],
    *,
    interactive: bool,
) -> object:
    """Run one managed stage after applying implicit or explicit transfer routing."""
    project_name, project_args = normalize_managed_args(stage.tokens)

    if project_name == MANAGED_EXPRESSION_PROJECT:
        if transfer:
            raise DispatchError("fallback expressions cannot receive chain positionals")
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

    routed = _route_transfer(argv, transfer)
    encoded = _encode_routed_values(routed, argv)
    return dispatcher.run(
        project_name,
        [*command.path, *encoded],
        interactive=interactive,
    )


def run_chain(
    dispatcher: Dispatcher,
    tokens: Sequence[str],
    *,
    interactive: bool = False,
    prompt: Callable[[str], str] | None = None,
) -> object:
    """Execute parsed stages left-to-right with invocation-local result transfer."""
    stages = parse_stages(tokens)
    result: object = None

    if interactive and prompt is None:
        from .cli import _prompt_required_value

        prompt = _prompt_required_value

    with chain_context_scope(), transfer_scope():
        for index, stage in enumerate(stages):
            transfer = [] if index == 0 else _transfer_values(result)
            if stage.kind is StageKind.SOLVE:
                values = [*(_literal_solve_transfer(value) for value in transfer), *stage.raw_tokens]
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
