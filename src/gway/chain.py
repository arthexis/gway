from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, Sequence
from typing import TYPE_CHECKING

from .chain_context import chain_context_scope, publish_chain_result
from .dispatcher.errors import DispatchError
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


def _run_reload_stage(
    runtime: GwayRuntime,
    stage_tokens: Sequence[str],
    raw_tokens: Sequence[str],
    transfer: Sequence[object],
    *,
    interactive: bool,
) -> None:
    """Checkpoint one active recipe and replace the current GWAY process."""
    if transfer:
        raise DispatchError("reload cannot receive chain positionals")
    if len(stage_tokens) != 1:
        raise DispatchError("reload does not accept arguments")

    from .runtime_reload import reload_runtime

    with runtime.frame_scope(
        "operation",
        operation="reload",
        tokens=raw_tokens,
    ) as frame:
        record(
            "runtime.operation.start",
            "executing GWAY operation",
            operation="reload",
            tokens=list(raw_tokens),
            frame_id=frame.id,
            parent_frame_id=frame.parent_id,
        )
        reload_runtime(runtime, interactive=interactive)
    raise RuntimeError("reload process replacement unexpectedly returned")


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
    if active_runtime.current_frame is None:
        with active_runtime.frame_scope("statement", tokens=tokens):
            return run_statement(
                dispatcher,
                tokens,
                interactive=interactive,
                prompt=prompt,
                context=context,
                provenance=provenance,
                runtime=active_runtime,
            )
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
            elif stage.tokens[0] == "reload":
                _run_reload_stage(
                    active_runtime,
                    stage.tokens,
                    stage.raw_tokens,
                    transfer,
                    interactive=interactive,
                )
                raise RuntimeError("reload process replacement unexpectedly returned")
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
