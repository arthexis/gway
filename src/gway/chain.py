from __future__ import annotations

from collections.abc import Callable, Mapping, MutableMapping, Sequence
from typing import TYPE_CHECKING

from .chain_context import chain_context_scope, publish_chain_result
from .dispatcher.errors import CommandNotFound, DispatchError
from .explain import record
from .expression import MANAGED_EXPRESSION_PROJECT, normalize_managed_args
from .outcome import CommandOutcome, SemanticFailure, resolve_outcome
from .provenance import ValueProvenance
from .solve import solve_values
from .stage import Stage, StageKind, parse_stages
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


def _stage_accepts_positional_transfer(dispatcher: Dispatcher, stage: Stage) -> bool:
    """Return whether a target can receive implicit positional transfer.

    ``Command.accepts_positional_transfer`` is deliberately tri-state. ``False``
    means the adapter positively knows the target accepts no positionals;
    ``True`` means it does; and ``None`` means the adapter has not described that
    capability, so legacy transfer behavior is preserved.
    """
    if not stage.tokens:
        return True

    project_name, project_args = normalize_managed_args(stage.tokens)
    if project_name == MANAGED_EXPRESSION_PROJECT:
        return True

    project = dispatcher.registry.get(project_name)
    if project is None:
        return True

    commands = dispatcher.commands(project.name)
    try:
        command, _ = dispatcher._resolve_command(commands, project_args)
    except CommandNotFound:
        if not project.default_command:
            return True
        command, _ = dispatcher._resolve_default_command(
            commands,
            project.default_command,
            project_args,
        )
    return command.accepts_positional_transfer is not False


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
    if len(stage_tokens) != 1:
        raise DispatchError("reload does not accept arguments")
    from .runtime_reload import reload_runtime

    with runtime.frame_scope("operation", operation="reload", tokens=raw_tokens) as frame:
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


def _record_semantic_failure(
    failure: SemanticFailure,
    stage: Stage,
    *,
    producer: ValueProvenance | None,
) -> None:
    """Record semantic failure at the evaluator boundary with producer provenance."""
    provenance = producer.as_dict() if producer is not None else None
    record(
        "runtime.operation.outcome",
        "evaluated explicit GWAY command outcome",
        operation=stage.tokens[0],
        success=False,
        result=failure.outcome.value,
        outcome_message=failure.outcome.message,
        provenance=provenance,
    )
    record(
        "chain.stage.failure",
        "chain stage reported semantic failure",
        operation=stage.tokens[0],
        result=failure.outcome.value,
        outcome_message=failure.outcome.message,
        provenance=provenance,
    )


def _resolve_stage_outcome(
    result: object,
    stage: Stage,
    *,
    producer: ValueProvenance | None,
) -> object:
    """Resolve an explicit semantic outcome before publishing a stage result."""
    if not isinstance(result, CommandOutcome):
        return result
    provenance = producer.as_dict() if producer is not None else None
    record(
        "runtime.operation.outcome",
        "evaluated explicit GWAY command outcome",
        operation=stage.tokens[0],
        success=result.success,
        result=result.value,
        outcome_message=result.message,
        provenance=provenance,
    )
    try:
        return resolve_outcome(result)
    except SemanticFailure as exc:
        record(
            "chain.stage.failure",
            "chain stage reported semantic failure",
            operation=stage.tokens[0],
            result=exc.outcome.value,
            outcome_message=exc.outcome.message,
            provenance=provenance,
        )
        raise


def run_statement(
    dispatcher: Dispatcher,
    tokens: Sequence[str],
    *,
    interactive: bool = False,
    prompt: Callable[[str], str] | None = None,
    context: MutableMapping[str, object] | None = None,
    provenance: MutableMapping[str, ValueProvenance] | None = None,
    runtime: GwayRuntime | None = None,
    start_stage_index: int = 0,
    initial_result: object = None,
    has_initial_result: bool = False,
    initial_result_provenance: ValueProvenance | None = None,
) -> object:
    """Execute one complete GWAY statement, optionally from a restored stage boundary."""
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
                start_stage_index=start_stage_index,
                initial_result=initial_result,
                has_initial_result=has_initial_result,
                initial_result_provenance=initial_result_provenance,
            )
    if provenance is None and context is not None:
        candidate = getattr(context, "provenance", None)
        if isinstance(candidate, MutableMapping):
            provenance = candidate
    stages = parse_stages(tokens)
    if start_stage_index < 0 or start_stage_index > len(stages):
        raise DispatchError("restored chain stage index is out of range")
    result: object = initial_result if has_initial_result else None
    result_provenance = initial_result_provenance if has_initial_result else None
    if start_stage_index:
        record(
            "resume.chain.restore",
            "restored pending chain at saved evaluator boundary",
            statement_tokens=list(tokens),
            completed_stages=start_stage_index,
            next_stage_index=start_stage_index + 1,
            total_stages=len(stages),
            has_previous_result=has_initial_result,
            previous_result=initial_result if has_initial_result else None,
            previous_result_provenance=(
                initial_result_provenance.as_dict()
                if initial_result_provenance is not None
                else None
            ),
        )
    record("chain.start", "executing command chain", stages=len(stages), tokens=list(tokens))

    if interactive and prompt is None:
        from .cli import _prompt_required_value

        prompt = _prompt_required_value

    statement_frame = active_runtime.current_frame
    recipe_path = statement_frame.recipe_path if statement_frame is not None else None
    recipe_line = statement_frame.recipe_line if statement_frame is not None else None
    with active_runtime.frames.chain_continuation_scope(
        statement_tokens=tokens,
        recipe_path=recipe_path,
        recipe_line=recipe_line,
    ) as chain_state:
        with chain_context_scope(context, provenance), transfer_scope():
            for index in range(start_stage_index, len(stages)):
                stage: Stage = stages[index]
                previous_result = result
                has_previous = index > start_stage_index or has_initial_result
                if chain_state is not None:
                    chain_state.active_stage_index = index + 1
                    chain_state.has_previous_result = has_previous
                    chain_state.previous_result = previous_result if has_previous else None
                    chain_state.previous_result_provenance = result_provenance if has_previous else None
                transfer = _transfer_values(previous_result) if has_previous else []
                if transfer and stage.kind is not StageKind.SOLVE and not _stage_accepts_positional_transfer(
                    dispatcher,
                    stage,
                ):
                    record(
                        "transfer.omit",
                        "omitted chain values because target accepts no positionals",
                        stage=index + 1,
                        tokens=list(stage.raw_tokens),
                        incoming=list(transfer),
                        reason="target accepts no positional parameters",
                    )
                    transfer = []
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
                    try:
                        result = active_runtime.execute_stage(
                            stage,
                            transfer,
                            interactive=interactive,
                            prompt=prompt,
                            previous_result=previous_result if has_previous else None,
                            has_previous_result=has_previous,
                        )
                    except SemanticFailure as exc:
                        producer = active_runtime.frames.value_provenance(
                            active_runtime.frames.last_completed
                        )
                        _record_semantic_failure(exc, stage, producer=producer)
                        raise
                    producer = active_runtime.frames.value_provenance(active_runtime.frames.last_completed)
                    result = _resolve_stage_outcome(result, stage, producer=producer)
                result_provenance = producer
                publish_chain_result(result, provenance=producer)
                record(
                    "chain.stage.result",
                    "published chain stage result",
                    stage=index + 1,
                    result=result,
                    provenance=producer.as_dict() if producer is not None else None,
                )

    record("chain.result", "command chain completed", result=result)
    if start_stage_index:
        record(
            "resume.chain.result",
            "completed restored pending chain",
            result=result,
            provenance=result_provenance.as_dict() if result_provenance is not None else None,
        )
    return result


def run_chain(
    dispatcher: Dispatcher,
    tokens: Sequence[str],
    *,
    interactive: bool = False,
    prompt: Callable[[str], str] | None = None,
) -> object:
    return run_statement(dispatcher, tokens, interactive=interactive, prompt=prompt)


__all__ = ["run_chain", "run_statement"]
