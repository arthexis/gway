from __future__ import annotations

import re
from collections.abc import Mapping, MutableMapping, Sequence
from dataclasses import dataclass

from ..dispatcher.errors import DispatchError
from ..explain import record
from ..provenance import ValueProvenance

_PARAMETER_NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_-]*\Z")
_RESERVED_PARAMETER_NAMES = frozenset({"result"})


@dataclass(frozen=True, slots=True)
class RecipeInvocation:
    """Parsed recipe path plus explicit named invocation parameters."""

    path: str
    parameters: dict[str, str]


def _parameter_key(name: str) -> str:
    if not _PARAMETER_NAME.fullmatch(name):
        raise DispatchError(
            f"invalid recipe parameter --{name}; names must start with a letter or underscore "
            "and contain only letters, numbers, dashes, or underscores"
        )
    key = name.replace("-", "_")
    if key in _RESERVED_PARAMETER_NAMES:
        raise DispatchError(f"recipe parameter --{name} is reserved by GWAY")
    return key


def parse_recipe_invocation(argv: Sequence[str]) -> RecipeInvocation:
    """Parse ``recipe PATH --name value`` without defining a recipe schema language."""
    operands = list(argv)
    literal_path = False
    if operands[:1] == ["--"]:
        literal_path = True
        operands = operands[1:]
    if not operands:
        raise DispatchError("recipe requires a .rx path")

    path = operands.pop(0)
    if not literal_path and path.startswith("-"):
        raise DispatchError("recipe paths beginning with '-' must follow the -- separator")

    parameters: dict[str, str] = {}
    index = 0
    while index < len(operands):
        token = operands[index]
        if token == "--" or not token.startswith("--"):
            raise DispatchError(
                "recipe parameters must use --name VALUE or --name=VALUE after the .rx path"
            )

        specification = token[2:]
        if "=" in specification:
            name, value = specification.split("=", 1)
        else:
            name = specification
            index += 1
            if index >= len(operands) or operands[index].startswith("--"):
                raise DispatchError(f"recipe parameter --{name} requires a value")
            value = operands[index]

        key = _parameter_key(name)
        if key in parameters:
            raise DispatchError(f"duplicate recipe parameter --{name}")
        parameters[key] = value
        index += 1

    return RecipeInvocation(path=path, parameters=parameters)


def seed_recipe_parameters(
    context: MutableMapping[str, object],
    parameters: Mapping[str, str],
    *,
    provenance: ValueProvenance | None = None,
) -> None:
    """Overlay explicit invocation values after inherited and chained recipe context."""
    if not parameters:
        return

    sidecar = getattr(context, "provenance", None)
    for key, value in parameters.items():
        context[key] = value
        if provenance is not None and isinstance(sidecar, MutableMapping):
            sidecar[key] = provenance

    record(
        "recipe.parameters",
        "seeded explicit recipe invocation parameters",
        origin="explicit",
        parameters=dict(parameters),
        provenance=provenance.as_dict() if provenance is not None else None,
    )


__all__ = [
    "RecipeInvocation",
    "parse_recipe_invocation",
    "seed_recipe_parameters",
]
