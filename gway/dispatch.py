"""Unified command resolution and dispatch for GWAY runtimes."""

from .adaptation import adapt_pipeline
from .binding import bind_arguments
from .tokens import chunk, token_value, tokenize

_MISSING = object()


def resolve_operation(runtime, tokens):
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

            # Temporary attribute fallback for wrapped operations exposed directly
            # on Gateway. Executable discovery otherwise belongs to runtime.ops.
            obj = runtime
            try:
                for part in candidate.replace(" ", ".").split("."):
                    obj = getattr(obj, part)
            except AttributeError:
                continue
            if callable(obj) and getattr(obj, "__gway_operation__", None) is not None:
                return obj, tokens[size:], candidate

    raise LookupError(f"Unable to resolve operation: {' '.join(values)}")


def dispatch_stage(
    runtime,
    tokens,
    *,
    pipeline=_MISSING,
    args=(),
    kwargs=None,
    allow_inline_with_native=False,
):
    """Resolve, bind, and execute one command stage."""
    kwargs = {} if kwargs is None else dict(kwargs)
    tokens = list(tokens)
    if not tokens:
        raise ValueError("Gateway command cannot be empty")

    func, arguments, _ = resolve_operation(runtime, tokens)

    if (args or kwargs) and arguments and not allow_inline_with_native:
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


def dispatch(runtime, command, *args, **kwargs):
    """Execute one or more command stages through the unified dispatcher."""
    tokens = tokenize(command) if isinstance(command, str) else list(command)
    if not tokens:
        raise ValueError("Gateway command cannot be empty")

    commands = chunk(tokens)
    if (args or kwargs) and len(commands) != 1:
        raise TypeError("Native arguments require a single operation")

    result = None
    for index, stage in enumerate(commands):
        result = dispatch_stage(
            runtime,
            stage,
            pipeline=result if index else _MISSING,
            args=args if index == 0 else (),
            kwargs=kwargs if index == 0 else None,
        )
    return result
