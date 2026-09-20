"""Unified command resolution and dispatch for GWAY runtimes."""

import ast
import os
from dataclasses import dataclass
from collections.abc import Mapping

from .adaptation import adapt_pipeline
from .binding import bind_arguments, pipeline_boundary
from .ingestion.base import expand_path
from .operations import Cardinality, singularize, subject_cardinality
from .recipes import execute_recipe, parse_recipe_context, recipe_path
from .semantic import AmbiguousKeyError, resolve_mapping_key
from .tokens import is_literal, statements, token_value, tokenize

_MISSING = object()


class CheckError(RuntimeError):
    """Raised when an atomic check does not satisfy its assertions."""


def _rollback_control_failure(runtime, rollback, primary):
    """Attempt one named rollback while preserving a control failure."""
    if rollback is not None:
        runtime.journal.rollback_after_failure(rollback, primary)
    return primary


def _check_stage(tokens):
    """Split one check control stage from a following dash pipeline."""
    stage = []
    remaining = []
    for index, token in enumerate(tokens):
        if index and not is_literal(token) and token_value(token) == "-":
            remaining = list(tokens[index + 1 :])
            break
        stage.append(token)
    return stage, remaining


def _check_expected(runtime, token):
    """Resolve one expected check value with lightweight literal coercion."""
    raw = token_value(token)
    if is_literal(token):
        return raw

    resolved = runtime.resolve(raw)
    if resolved is not raw and resolved != raw:
        return resolved

    lowered = raw.casefold()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered in {"none", "null"}:
        return None

    try:
        return ast.literal_eval(raw)
    except (ValueError, SyntaxError):
        return raw


def _check_options(runtime, tokens):
    """Parse atomic check assertions from raw control-stage tokens."""
    tokens = list(tokens)
    checks = []
    rollback = None
    index = 1

    while index < len(tokens):
        option_token = tokens[index]
        option = token_value(option_token)
        literal_option = is_literal(option_token)
        if not option.startswith("--"):
            raise TypeError(f"Unexpected check argument {option!r}")

        if not literal_option and option in {"--true", "--false"}:
            checks.append(("boolean", option == "--true", None))
            index += 1
            continue

        if not literal_option and option == "--is":
            if index + 1 >= len(tokens):
                raise TypeError("Expected a value after --is")
            checks.append(("is", _check_expected(runtime, tokens[index + 1]), None))
            index += 2
            continue

        if not literal_option and option == "--rollback":
            if rollback is not None:
                raise TypeError("check accepts only one --rollback journal")
            if index + 1 >= len(tokens):
                raise TypeError("Expected a journal name after --rollback")
            rollback_token = tokens[index + 1]
            rollback_raw = token_value(rollback_token)
            if (
                not is_literal(rollback_token)
                and rollback_raw.startswith("--")
            ):
                raise TypeError("Expected a journal name after --rollback")
            rollback = str(rollback_raw)
            index += 2
            continue

        inverted = not literal_option and option.startswith("--no-")
        name = option[5:] if inverted else option[2:]
        if not name:
            raise TypeError(f"Invalid check argument {option!r}")

        expected = _MISSING
        if index + 1 < len(tokens):
            next_token = tokens[index + 1]
            next_raw = token_value(next_token)
            if is_literal(next_token) or (
                not next_raw.startswith("--") and next_raw != "-"
            ):
                expected = _check_expected(runtime, next_token)
                index += 1

        checks.append(("mapping", name, (inverted, expected)))
        index += 1

    if not checks:
        raise TypeError("check requires at least one assertion")
    return checks, rollback


def _execute_check(runtime, tokens, result):
    """Apply atomic assertions to one result and return it unchanged."""
    checks, rollback = _check_options(runtime, tokens)

    try:
        for kind, value, detail in checks:
            if kind == "boolean":
                if not isinstance(result, bool):
                    raise CheckError("check --true/--false requires a boolean result")
                if result is not value:
                    raise CheckError(
                        f"check expected result to be {str(value).lower()}"
                    )
                continue

            if kind == "is":
                if result != value:
                    raise CheckError(
                        f"check expected result to equal {value!r}; got {result!r}"
                    )
                continue

            if not isinstance(result, Mapping):
                raise CheckError(
                    f"check --{value} requires a mapping result; "
                    f"got {type(result).__name__}"
                )

            inverted, expected = detail
            try:
                actual_key = resolve_mapping_key(result, value)
            except AmbiguousKeyError as exception:
                raise CheckError(str(exception)) from exception
            except KeyError:
                actual_key = _MISSING

            present = actual_key is not _MISSING
            if expected is _MISSING:
                passed = not present if inverted else present
                if not passed:
                    expectation = "absent" if inverted else "present"
                    raise CheckError(
                        f"check expected key {value!r} to be {expectation}"
                    )
                continue

            actual = result[actual_key] if present else _MISSING
            matches = present and actual == expected
            passed = not matches if inverted else matches
            if not passed:
                if inverted:
                    raise CheckError(
                        f"check expected key {value!r} not to equal {expected!r}"
                    )
                if actual is _MISSING:
                    raise CheckError(
                        f"check expected key {value!r} to be present"
                    )
                raise CheckError(
                    f"check expected key {value!r} to equal {expected!r}; "
                    f"got {actual!r}"
                )
    except CheckError as primary:
        _rollback_control_failure(runtime, rollback, primary)
        raise

    return result


@dataclass(frozen=True)
class ResolvedOperation:
    """One resolved callable plus per-invocation semantic subject intent."""

    callable: object
    arguments: list
    candidate: str
    subject: str | None = None
    cardinality: object = None

    def __iter__(self):
        yield self.callable
        yield self.arguments
        yield self.candidate


def _resolved(func, arguments, candidate):
    subject = getattr(func, "__gway_subject__", None)
    requested = candidate.replace(" ", ".").split(".")[-1]
    cardinality = (
        subject_cardinality(requested, subject) if subject is not None else None
    )
    return ResolvedOperation(
        func,
        arguments,
        candidate,
        subject=subject,
        cardinality=cardinality,
    )


def _expand_candidate(runtime, candidate):
    """JIT-expand hierarchical and semantic branches for one candidate."""
    path = tuple(part for part in candidate.replace(" ", ".").split(".") if part)
    expanded = False
    for size in range(1, len(path) + 1):
        expanded = expand_path(runtime, path[:size]) or expanded

    if len(path) >= 2:
        semantic_branch = (*path[:-2], path[-1])
        expanded = expand_path(runtime, semantic_branch) or expanded
        singular = singularize(path[-1])
        if singular is not None:
            singular_branch = (*path[:-2], singular)
            expanded = expand_path(runtime, singular_branch) or expanded

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
                return _resolved(value, tokens[size:], candidate)
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
                return _resolved(value, tokens[size:], candidate)

            if _expand_candidate(runtime, candidate):
                value = runtime.ops.resolve(candidate)
                if callable(value):
                    return _resolved(value, tokens[size:], candidate)

            obj = runtime
            try:
                for part in candidate.replace(" ", ".").split("."):
                    obj = getattr(obj, part)
            except AttributeError:
                continue
            if callable(obj) and getattr(obj, "__gway_operation__", None) is not None:
                return _resolved(obj, tokens[size:], candidate)

    if pipeline is not _MISSING:
        semantic = _semantic_pipeline_operation(runtime, tokens, pipeline)
        if semantic is not None:
            return semantic

    raise LookupError(f"Unable to resolve operation: {' '.join(values)}")


def _enforce_cardinality(resolution, result):
    """Apply semantic ONE/MANY intent to collection-producing operations."""
    if resolution.cardinality is None:
        return result

    kind = getattr(resolution.callable, "__gway_source_kind__", None)
    if kind != "django-manager":
        return result

    if resolution.cardinality is Cardinality.MANY:
        return result

    if isinstance(result, (str, bytes, bytearray, Mapping)):
        return result

    subject = resolution.subject or "result"

    if hasattr(result, "__getitem__") and hasattr(result, "__iter__"):
        try:
            selected = list(result[:2])
        except (TypeError, KeyError, IndexError):
            selected = None
        if selected is not None:
            if not selected:
                raise LookupError(f"No {subject} matched the query")
            if len(selected) > 1:
                raise LookupError(
                    f"Expected one {subject}; query matched multiple results. "
                    f"Use the plural subject to allow multiple results."
                )
            return selected[0]

    return result


def _invoke_resolved(runtime, resolution, *args, **kwargs):
    """Invoke one resolved operation and keep published state cardinality-consistent."""
    subject = resolution.subject
    results = runtime.results
    history_size = len(results.history)
    had_subject = subject is not None and subject in results.maps[0]
    previous = results.maps[0].get(subject) if had_subject else None

    try:
        raw = resolution.callable(*args, **kwargs)
        normalized = _enforce_cardinality(resolution, raw)
    except Exception:
        del results.history[history_size:]
        if subject is not None:
            if had_subject:
                results.maps[0][subject] = previous
            else:
                results.maps[0].pop(subject, None)
        raise

    if normalized is not raw and len(results.history) > history_size:
        results.history[-1] = normalized
        if subject is not None and results.maps[0].get(subject) is raw:
            results.maps[0][subject] = normalized
    return normalized


def _recipe_source(token):
    return token if isinstance(token, os.PathLike) else token_value(token)


def _split_recipe_stage(tokens):
    """Split one recipe invocation from a following raw pipeline."""
    tokens = list(tokens)
    for index, token in enumerate(tokens[1:], start=1):
        if not is_literal(token) and token_value(token) == "-":
            return tokens[:index], tokens[index + 1 :]
    return tokens, []


def _resolve_recipe_stage(runtime, tokens, *, pipeline=_MISSING):
    """Resolve a recipe stage using explicit-path then operation-safe fallback."""
    if not tokens:
        return None

    source = _recipe_source(tokens[0])
    explicit = recipe_path(runtime, source, allow_bare=False)
    if explicit is not None:
        stage, remaining = _split_recipe_stage(tokens)
        return explicit, stage[1:], remaining

    bare = recipe_path(runtime, source, allow_bare=True)
    if bare is None:
        return None

    try:
        resolve_operation(runtime, tokens, pipeline=pipeline)
    except LookupError:
        stage, remaining = _split_recipe_stage(tokens)
        return bare, stage[1:], remaining
    return None


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

    resolution = resolve_operation(runtime, tokens, pipeline=pipeline)
    func, arguments, _ = resolution

    if (args or kwargs) and arguments:
        raise TypeError(
            "Native arguments require an operation name without inline arguments"
        )

    initial_args = tuple(args)
    initial_kwargs = kwargs
    if pipeline is not _MISSING:
        receiver = getattr(func, "__gway_receiver__", None)
        producer_subject = runtime.results.subject(pipeline)
        pipeline_is_receiver = receiver is not None and producer_subject == receiver

        if arguments and not pipeline_is_receiver:
            bound = bind_arguments(
                func,
                arguments,
                runtime=runtime,
                interactive=runtime.interactive_enabled,
                initial_args=initial_args,
                initial_kwargs=initial_kwargs,
                pipeline=pipeline,
            )
            return _invoke_resolved(runtime, resolution, *bound.args, **bound.kwargs)

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
        return _invoke_resolved(runtime, resolution, *bound.args, **bound.kwargs)

    if pipeline is not _MISSING:
        return _invoke_resolved(runtime, resolution, *initial_args, **initial_kwargs)

    if args or kwargs:
        return _invoke_resolved(runtime, resolution, *args, **kwargs)

    bound = bind_arguments(
        func,
        (),
        runtime=runtime,
        interactive=runtime.interactive_enabled,
    )
    return _invoke_resolved(runtime, resolution, *bound.args, **bound.kwargs)


def split_stage(
    runtime,
    tokens,
    *,
    pipeline=_MISSING,
    args=(),
    kwargs=None,
):
    """Split the first executable stage from the remaining raw pipeline."""
    tokens = list(tokens)
    func, arguments, _ = resolve_operation(runtime, tokens, pipeline=pipeline)

    initial_args = tuple(args)
    initial_kwargs = {} if kwargs is None else dict(kwargs)
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

    boundary = pipeline_boundary(
        func,
        arguments,
        initial_args=initial_args,
        initial_kwargs=initial_kwargs,
    )
    if boundary is None:
        return tokens, []

    if args or kwargs:
        raise TypeError("Native arguments require a single operation")

    operation_size = len(tokens) - len(arguments)
    return (
        tokens[: operation_size + boundary],
        arguments[boundary + 1 :],
    )


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

        if not is_literal(remaining[0]) and token_value(remaining[0]) == "check":
            if stage_args or stage_kwargs:
                raise TypeError("Native arguments are not supported for check")
            stage, remaining = _check_stage(remaining)
            if current is _MISSING:
                current = runtime.results.last
            result = _execute_check(runtime, stage, current)
            results.append(result)
            current = result
            first = False
            continue

        recipe = _resolve_recipe_stage(
            runtime,
            remaining,
            pipeline=current,
        )
        if recipe is not None:
            if stage_args or stage_kwargs:
                raise TypeError("Native arguments are not supported for recipe stages")
            path, recipe_arguments, remaining = recipe
            context = parse_recipe_context(recipe_arguments)
            if current is _MISSING:
                _, result = execute_recipe(runtime, path, context=context)
            else:
                _, result = execute_recipe(
                    runtime,
                    path,
                    context=context,
                    pipeline=current,
                )
            results.append(result)
            current = result
            first = False
            continue

        stage, remaining = split_stage(
            runtime,
            remaining,
            pipeline=current,
            args=stage_args,
            kwargs=stage_kwargs,
        )

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


def dispatch_program(
    runtime,
    statement_list,
    *,
    pipeline=_MISSING,
    args=(),
    kwargs=None,
):
    """Execute statements within one nested execution scope."""
    with runtime.execution_scope():
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
                pipeline=pipeline if index == 0 else _MISSING,
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
    if isinstance(command, str):
        tokens = tokenize(command)
    elif isinstance(command, os.PathLike):
        tokens = [command]
    else:
        tokens = list(command)
    if not tokens:
        raise ValueError("Gateway command cannot be empty")

    _, result = dispatch_program(
        runtime,
        statements(tokens),
        args=args,
        kwargs=kwargs,
    )
    return result
