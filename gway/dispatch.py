"""Unified command resolution and dispatch for GWAY runtimes."""

from .adaptation import adapt_pipeline
from .binding import bind_arguments, pipeline_boundary
from .ingestion.base import expand_path
from .tokens import statements, token_value, tokenize

_MISSING = object()


def _expand_candidate(runtime, candidate):
    """JIT-expand hierarchical and semantic branches for one candidate."""
    path = tuple(part for part in candidate.replace(" ", ".").split(".") if part)
    expanded = False
    for size in range(1, len(path) + 1):
        expanded = expand_path(runtime, path[:size]) or expanded

    if len(path) >= 2:
        semantic_branch = (*path[:-2], path[-1])
        expanded = expand_path(runtime, semantic_branch) or expanded

    return expanded


def _semantic_pipeline_operation(runtime, tokens, pipeline):
    """Resolve a bare operation against the semantic subject of a pipeline value."""
    subject = runtime.results.subject(pipeline)
    if subject is None:
        return None

    expand_path(runtime, (subject,))
    values = [token_value(token) for token in tokens]
    for size in range(len(values), 0, -1):
        candidates = (
            " ".join(values[:size]),
            "_".join(token.replace("-", "_") for token in values[:size]),
            ".".join(token.replace("-", "_") for token in values[:size]),
        )
        for candidate in candidates:
            value = runtime.ops.resolve_pair(candidate, subject)
            if callable(value):
                return value, tokens[size:], candidate
    return None


def resolve_operation(runtime, tokens, *, pipeline=_MISSING):
    """Resolve the longest leading token sequence to an executable operation."""
    values = [token_value(token) for token in tokens]
    for size in range(len(values), 0, -1):
        candidates = (
            " ".join(values[:size]),
            "_".join(token.replace("-", "_") for token in values[:size]),
            ".".join(token.replace("-", "_") for token in values[:size]),
        )
        for candidate in candidates:
            value = runtime.ops.resolve(candidate)
            if callable(value):
                return value, tokens[size:], candidate

            if _expand_candidate(runtime, candidate):
                value = runtime.ops.resolve(candidate)
                if callable(value):
                    return value, tokens[size:], candidate

            obj = runtime
            try:
                for part in candidate.replace(" ", ".").split("."):
                    obj = getattr(obj, part)
            except AttributeError:
                continue
            if callable(obj) and getattr(obj, "__gway_operation__", None) is not None:
                return obj, tokens[size:], candidate

    if pipeline is not _MISSING:
        semantic = _semantic_pipeline_operation(runtime, tokens, pipeline)
        if semantic is not None:
            return semantic

    raise LookupError(f"Unable to resolve operation: {' '.join(values)}")


def dispatch_stage(
    runtime,
    tokens,
    *,
    pipeline=_MISSING,
    args=(),
    kwargs=None,
):
    """Resolve, bind, and execute one command stage."""
    kwargs = {} if kwargs is None else dict(kwargs)
    tokens = list(tokens)
    if not tokens:
        raise ValueError("Gateway command cannot be empty")

    func, arguments, _ = resolve_operation(runtime, tokens, pipeline=pipeline)

    if (args or kwargs) and arguments:
        raise TypeError(
            "Native arguments require an operation name without inline arguments"
        )

    initial_args = tuple(args)
    initial_kwargs = kwargs
    if pipeline is not _MISSING:
        adapted = adapt_pipeline(
            runtime,
            func,
            pipeline,
            args=initial_args,
            kwargs=initial_kwargs,
        )
        initial_args = adapted.args
        initial_kwargs = adapted.kwargs

    if arguments:
        bound = bind_arguments(
            func,
            arguments,
            runtime=runtime,
            interactive=runtime.interactive_enabled,
            initial_args=initial_args,
            initial_kwargs=initial_kwargs,
        )
        return func(*bound.args, **bound.kwargs)

    if pipeline is not _MISSING:
        return func(*initial_args, **initial_kwargs)

    if args or kwargs:
        return func(*args, **kwargs)

    bound = bind_arguments(
        func,
        (),
        runtime=runtime,
        interactive=runtime.interactive_enabled,
    )
    return func(*bound.args, **bound.kwargs)



def dispatch_pipeline(
    runtime,
    tokens,
    *,
    pipeline=_MISSING,
    args=(),
    kwargs=None,
):
    """Execute one statement, transferring raw results only across dash pipes."""
    remaining = list(tokens)
    if not remaining:
        raise ValueError("Gateway command cannot be empty")

    results = []
    current = pipeline
    first = True

    while remaining:
        stage_args = args if first else ()
        stage_kwargs = kwargs if first else None
        func, arguments, _ = resolve_operation(runtime, remaining, pipeline=current)

        initial_args = tuple(stage_args)
        initial_kwargs = {} if stage_kwargs is None else dict(stage_kwargs)
        if current is not _MISSING:
            adapted = adapt_pipeline(
                runtime,
                func,
                current,
                args=initial_args,
                kwargs=initial_kwargs,
            )
            initial_args = adapted.args
            initial_kwargs = adapted.kwargs

        boundary = pipeline_boundary(
            func,
            arguments,
            initial_args=initial_args,
            initial_kwargs=initial_kwargs,
        )
        operation_size = len(remaining) - len(arguments)

        if boundary is None:
            stage = remaining
            remaining = []
        else:
            if stage_args or stage_kwargs:
                raise TypeError("Native arguments require a single operation")
            stage = remaining[: operation_size + boundary]
            remaining = arguments[boundary + 1 :]

        result = dispatch_stage(
            runtime,
            stage,
            pipeline=current,
            args=stage_args,
            kwargs=stage_kwargs,
        )
        results.append(result)
        current = result
        first = False

    return results, current


def dispatch_program(runtime, statement_list, *, args=(), kwargs=None):
    """Execute statements without raw transfer across statement boundaries."""
    statement_list = [list(statement) for statement in statement_list if statement]
    if not statement_list:
        raise ValueError("Gateway command cannot be empty")
    if (args or kwargs) and len(statement_list) != 1:
        raise TypeError("Native arguments require a single statement")

    results = []
    last = None
    for index, statement in enumerate(statement_list):
        produced, last = dispatch_pipeline(
            runtime,
            statement,
            args=args if index == 0 else (),
            kwargs=kwargs if index == 0 else None,
        )
        results.extend(produced)
    return results, last

def dispatch_sequence(
    runtime,
    stages,
    *,
    pipeline=_MISSING,
    args=(),
    kwargs=None,
):
    """Execute an ordered sequence of stages with one shared pipeline contract."""
    stages = [list(stage) for stage in stages if stage]
    if not stages:
        raise ValueError("Gateway command cannot be empty")
    if (args or kwargs) and len(stages) != 1:
        raise TypeError("Native arguments require a single operation")

    results = []
    current = pipeline
    for index, stage in enumerate(stages):
        stage_kwargs = kwargs if index == 0 else None
        stage_args = args if index == 0 else ()
        if current is _MISSING:
            result = dispatch_stage(
                runtime,
                stage,
                args=stage_args,
                kwargs=stage_kwargs,
            )
        else:
            result = dispatch_stage(
                runtime,
                stage,
                pipeline=current,
                args=stage_args,
                kwargs=stage_kwargs,
            )
        results.append(result)
        current = result
    return results, current


def dispatch(runtime, command, *args, **kwargs):
    """Execute one or more statements through the unified dispatcher."""
    tokens = tokenize(command) if isinstance(command, str) else list(command)
    if not tokens:
        raise ValueError("Gateway command cannot be empty")

    _, result = dispatch_program(
        runtime,
        statements(tokens),
        args=args,
        kwargs=kwargs,
    )
    return result
