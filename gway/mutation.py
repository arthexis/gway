"""Reserved mutation semantics for callable-backed Gway operations."""

import inspect


MUTATE_PARAMETER = "mutate"
MUTATE_UNSET = object()


class MutationError(RuntimeError):
    """Raised when an operation cannot honor a non-mutating execution."""


def mutation_parameter(callable_):
    """Return the reserved mutate parameter declared by a callable, if any."""
    try:
        signature = inspect.signature(callable_)
    except (TypeError, ValueError):
        return None

    parameter = signature.parameters.get(MUTATE_PARAMETER)
    if parameter is None:
        return None
    if parameter.kind not in (
        inspect.Parameter.POSITIONAL_OR_KEYWORD,
        inspect.Parameter.KEYWORD_ONLY,
    ):
        raise TypeError(
            "reserved mutate parameter must be positional-or-keyword or keyword-only"
        )
    if parameter.default is inspect.Parameter.empty or (
        parameter.default is not MUTATE_UNSET
        and not isinstance(parameter.default, bool)
    ):
        raise TypeError(
            "reserved mutate parameter must default to True or False "
            "(or Gway's internal unset policy)"
        )
    return parameter


def supports_no_mutate(callable_):
    """Return whether a callable explicitly supports Gway's mutation contract."""
    declared = getattr(callable_, "__gway_supports_no_mutate__", None)
    if declared is not None:
        return bool(declared)
    return mutation_parameter(callable_) is not None


def mutates(callable_):
    """Return the callable's declared default mutation behavior.

    Wrapped operations retain their original mutation metadata even though the
    reserved mutate parameter is hidden from the public signature. Callables
    without an explicit contract remain conservatively classified as mutating.
    """
    declared = getattr(callable_, "__gway_mutates__", None)
    if declared is not None:
        return bool(declared)
    parameter = mutation_parameter(callable_)
    if parameter is None or parameter.default is MUTATE_UNSET:
        return True
    return parameter.default


def public_signature(callable_, *, receiver=False):
    """Return the user-facing signature with reserved mutation semantics hidden."""
    try:
        signature = inspect.signature(callable_)
    except (TypeError, ValueError):
        return None

    parameters = list(signature.parameters.values())
    if receiver and parameters:
        parameters = parameters[1:]
    parameters = [
        parameter
        for parameter in parameters
        if parameter.name != MUTATE_PARAMETER
    ]
    return signature.replace(parameters=parameters)



def rollback_with(operation):
    """Declare an explicit semantic inverse for an operation.

    Most operations should rely on conventional inverse verbs. Use this only
    when the rollback operation cannot be inferred from the shared subject.
    """

    def decorate(callable_):
        callable_.__gway_rollback__ = operation
        return callable_

    return decorate
