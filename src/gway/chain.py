from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, Sequence
from typing import TYPE_CHECKING

from .chain_context import chain_context_scope, publish_chain_result
from .explain import record
from .provenance import ValueProvenance
from .solve import solve_values
from .stage import StageKind, parse_stages
from .transfer import transfer_scope

if TYPE_CHECKING:
    from .dispatcher import Dispatcher
    from .runtime import GwayRuntime


def _transfer_values(result: object) -> list[object]:
    if result is None or isinstance(result, Mapping):
        return []
    if isinstance(result, Sequence) and not isinstance(result, (str, bytes, bytearray)):
        return list(result)
    return [result]


def _literal_solve_transfer(value: object) -> str:
    if isinstance(value, bytes):
        text = value.decode(errors="replace")
    elif isinstance(value, bytearray):
        text = bytes(value).decode(errors="replace")
    else:
        text = str(value)
    return text.replace("[", "[[").replace("]", "]]" )


def run_statement(
    dispatcher: Dispatcher,
    tokens: Sequence[str],
    *,
    interactive: bool = False,
    prompt: Callable[[str], str] | None = None,
    context: MutableMapping[str, object] | None = None,
    provenance: MutableMapping[str, ValueProvenance] | None = None,
    runtime: GwayRuntime | None = None,
) -> object:
    """Execute one complete GWAY statement in an optional caller-owned context."""
    from .runtime import GwayRuntime

    active_runtime = runtime or GwayRuntime(dispatcher)
    if provenance is None and context is not None:
        candidate = getattr(context, "provenance", None)
        if isinstance(candidate, MutableMapping):
            provenance = candidate
    stages = parse_stages(tokens)
    result: object = None
    record("chain.start", "executing command chain", stages=len(stages), tokens=list(tokens))

    if interactive and prompt is None:
        from .cli import _prompt_required_value

        prompt = _prompt_required_value

    with chain_context_scope(context, provenance), transfer_scope():
        for index, stage in enumerate(stages):
            previous_result = result
            transfer = [] if index == 0 else _transfer_values(previous_result)
            record(
                "chain.stage.start",
                "executing chain stage",
                stage=index + 1,
                stage_kind=stage.kind.value,
                tokens=list(stage.raw_tokens),
                transfer=list(transfer),
            )
            producer: ValueProvenance | None
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
                producer = active_runtime.frames.value_provenance(active_runtime.current_frame)
            else:
                result = active_runtime.execute_stage(
                    stage,
                    transfer,
                    interactive=interactive,
                    prompt=prompt,
                    previous_result=previous_result if index else None,
                    has_previous_result=index > 0,
                )
                producer = active_runtime.frames.value_provenance(
                    active_runtime.frames.last_completed
                )
            publish_chain_result(result, provenance=producer)
            record(
                "chain.stage.result",
                "published chain stage result",
                stage=index + 1,
                result=result,
                provenance=producer.as_dict() if producer is not None else None,
            )

    record("chain.result", "command chain completed", result=result)
    return result


def run_chain(
    dispatcher: Dispatcher,
    tokens: Sequence[str],
    *,
    interactive: bool = False,
    prompt: Callable[[str], str] | None = None,
) -> object:
    """Execute a command chain with a fresh invocation-local context."""
    return run_statement(
        dispatcher,
        tokens,
        interactive=interactive,
        prompt=prompt,
    )


__all__ = ["run_chain", "run_statement"]
