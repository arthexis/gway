"""First-class operation wrappers for recipe entry points."""

import inspect
from pathlib import Path

from ..ingestion.base import IngestedOperation, register_operation
from . import execute_recipe
from .contract import recipe_contract


def _operation_callable(runtime, recipe, signature, doc):
    recipe = Path(recipe).expanduser().resolve()

    def invoke(*args, **kwargs):
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()
        context = {}
        for name, value in bound.arguments.items():
            if name == "mutate":
                continue
            parameter = signature.parameters[name]
            if parameter.kind is inspect.Parameter.VAR_KEYWORD:
                context.update(value)
            elif parameter.kind is inspect.Parameter.VAR_POSITIONAL:
                context[name] = tuple(value)
            else:
                context[name] = value
        _, result = execute_recipe(runtime, recipe, context=context)
        return result

    invoke.__name__ = recipe.stem if recipe.stem != "__main__" else recipe.parent.name
    invoke.__doc__ = doc or f"Execute first-class recipe operation {invoke.__name__!r}."
    invoke.__signature__ = signature
    return invoke


def register_recipe_operation(runtime, name, recipe, *, route_name, root):
    """Register one recipe as a normal Gway operation unless already claimed."""
    recipe = Path(recipe).expanduser().resolve()
    signature, doc, companion = recipe_contract(recipe)
    callable_ = _operation_callable(runtime, recipe, signature, doc)

    operation = IngestedOperation(
        tuple(part for part in str(name).replace(" ", ".").split(".") if part),
        callable_,
        source=recipe,
        kind="recipe",
        metadata={
            "recipe": str(recipe),
            "companion": str(companion) if companion is not None else None,
            "route": str(route_name),
            "root": Path(root).expanduser().resolve(),
        },
    )

    existing = runtime.ops.resolve(operation.name)
    if existing is not None:
        return None
    return register_operation(runtime, operation)
