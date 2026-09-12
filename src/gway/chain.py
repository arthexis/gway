from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .chain_context import chain_context_scope, publish_chain_result
from .dispatcher.errors import CommandNotFound, DispatchError
from .explain import record
from .expression import MANAGED_EXPRESSION_PROJECT, normalize_managed_args
from .solve import solve_values
from .stage import Stage, StageKind, parse_stages
from .transfer import encode_transfer, transfer_scope

if TYPE_CHECKING:
    from .dispatcher import Dispatcher

_SELECTOR = re.compile(r"\[(?P<index>[1-9]\d*)\]\Z")
_WILDCARD = "[*]"


@dataclass(frozen=True, slots=True)
class _Transferred:
    value: object


def _transfer_values(result: object) -> list[object]:
    if result is None or isinstance(result, Mapping):
        return []
    if isinstance(result, Sequence) and not isinstance(result, (str, bytes, bytearray)):
        return list(result)
    return [result]


def _selector_index(token: str) -> int | None:
    match = _SELECTOR.fullmatch(token)
    return int(match.group("index")) if match is not None else None


def _route_transfer(
    argv: Sequence[str],
    transfer: Sequence[object],
    *,
    selector_tokens: Sequence[str] | None = None,
) -> list[str | _Transferred]:
    selectors = argv if selector_tokens is None else selector_tokens
    numeric = [_selector_index(token) for token in selectors]
    explicit = any(index is not None for index in numeric) or _WILDCARD in selectors
    if not explicit:
        return [*(_Transferred(value) for value in transfer), *argv]

    if selectors.count(_WILDCARD) > 1:
        raise DispatchError("a chain stage may contain at most one [*] selector")

    selected = {index for index in numeric if index is not None}
    if selected and max(selected) > len(transfer):
        missing = max(selected)
        raise DispatchError(
            f"chain transfer selector [{missing}] is out of range for {len(transfer)} value(s)"
        )

    remainder = [value for index, value in enumerate(transfer, start=1) if index not in selected]
    routed: list[str | _Transferred] = []
    for token, selector, index in zip(argv, selectors, numeric, strict=True):
        if index is not None:
            routed.append(_Transferred(transfer[index - 1]))
        elif selector == _WILDCARD:
            routed.extend(_Transferred(value) for value in remainder)
        else:
            routed.append(token)
    return routed


def _encode_transfer_value(value: object) -> str:
    if isinstance(value, (str, bytes, bytearray)):
        return encode_transfer(value)
    if isinstance(value, (bool, int, float, Path)):
        return str(value)
    return encode_transfer(value)


def _encode_routed_values(values: Sequence[str | _Transferred]) -> list[str]:
    return [
        _encode_transfer_value(value.value) if isinstance(value, _Transferred) else value
        for value in values
    ]


def _literal_solve_transfer(value: object) -> str:
    if isinstance(value, bytes):
        text = value.decode(errors="replace")
    elif isinstance(value, bytearray):
        text = bytes(value).decode(errors="replace")
    else:
        text = str(value)
    return text.replace("[", "[[").replace("]", "]]" )


def _run_command_stage(
    dispatcher: Dispatcher,
    stage: Stage,
    transfer: Sequence[object],
    *,
    interactive: bool,
) -> object:
    project_name, project_args = normalize_managed_args(stage.tokens)
    _, raw_project_args = normalize_managed_args(stage.raw_tokens)

    if project_name == MANAGED_EXPRESSION_PROJECT:
        if transfer:
            raise DispatchError("fallback expressions cannot receive chain positionals")
        return dispatcher.run(project_name, project_args, interactive=interactive)

    project = dispatcher.registry.require(project_name)
    commands = dispatcher.commands(project_name)
    used_default = False
    try:
        command, argv = dispatcher._resolve_command(commands, project_args)
    except CommandNotFound:
        if not project.default_command:
            raise
        used_default = True
        command, argv = dispatcher._resolve_default_command(
            commands,
            project.default_command,
            project_args,
        )

    raw_argv = raw_project_args if used_default else raw_project_args[len(command.path) :]
    alias_arguments = (project.alias_arguments or {}).get(project_name, ())
    combined_argv = [*alias_arguments, *argv]
    selector_tokens = [*("" for _ in alias_arguments), *raw_argv]
    routed = _route_transfer(combined_argv, transfer, selector_tokens=selector_tokens)
    encoded = _encode_routed_values(routed)
    record(
        "transfer.route",
        "routed chain values into command arguments",
        project=project.name,
        command=list(command.path),
        incoming=list(transfer),
        selectors=list(selector_tokens),
        outgoing=list(encoded),
    )
    return dispatcher.run(
        project.name,
        [*command.path, *encoded],
        interactive=interactive,
    )


def run_chain(
    dispatcher: Dispatcher,
    tokens: Sequence[str],
    *,
    interactive: bool = False,
    prompt: Callable[[str], str] | None = None,
    context: dict[str, object] | None = None,
) -> object:
    stages = parse_stages(tokens)
    result: object = None
    record("chain.start", "executing command chain", stages=len(stages), tokens=list(tokens))

    if interactive and prompt is None:
        from .cli import _prompt_required_value

        prompt = _prompt_required_value

    with chain_context_scope(context), transfer_scope():
        for index, stage in enumerate(stages):
            transfer = [] if index == 0 else _transfer_values(result)
            record(
                "chain.stage.start",
                "executing chain stage",
                stage=index + 1,
                stage_kind=stage.kind.value,
                tokens=list(stage.raw_tokens),
                transfer=list(transfer),
            )
            if stage.kind is StageKind.SOLVE:
                values = [
                    *(_literal_solve_transfer(value) for value in transfer),
                    *stage.raw_tokens,
                ]
                record(
                    "transfer.route",
                    "routed chain values into solve stage",
                    stage=index + 1,
                    incoming=list(transfer),
                    outgoing=list(values),
                )
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
            record(
                "chain.stage.result",
                "published chain stage result",
                stage=index + 1,
                result=result,
            )

    record("chain.result", "command chain completed", result=result)
    return result


__all__ = ["run_chain"]
