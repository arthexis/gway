"""Recipe-tree ingestion for explicit filesystem directories."""

from pathlib import Path

from .base import IngestedOperation, canonical_name, normalize_path, register_operation


def is_recipe_tree(path):
    """Return whether a directory contains at least one recipe descendant."""
    path = Path(path).expanduser()
    return path.is_dir() and any(path.rglob("*.rx"))


def _recipe_segments(root, recipe):
    """Return semantic segments for one recipe relative to an ingested tree."""
    relative = recipe.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if not parts:
        return ()

    stem = parts[-1]
    parent_name = recipe.parent.name
    if stem == "__main__" or stem == parent_name:
        parts.pop()
    return tuple(parts)


def _recipe_callable(gateway, recipe):
    """Create an ordinary Gway operation that executes one recipe path."""
    recipe = Path(recipe).expanduser().resolve()

    def invoke(*pipeline, **context):
        from ..recipes import execute_recipe

        if not pipeline:
            _, result = execute_recipe(gateway, recipe, context=context)
            return result

        incoming = pipeline[0] if len(pipeline) == 1 else tuple(pipeline)
        _, result = execute_recipe(
            gateway,
            recipe,
            context=context,
            pipeline=incoming,
        )
        return result

    invoke.__name__ = recipe.stem
    invoke.__doc__ = f"Run recipe {recipe}."
    return invoke


def ingest_recipe_tree(gateway, directory, *, path=None, **kwargs):
    """Recursively expose recipes beneath a directory as one semantic tree."""
    directory = Path(directory).expanduser().resolve()
    if not directory.is_dir():
        raise ValueError(f"Recipe tree is not a directory: {directory}")

    recipes = sorted(item for item in directory.rglob("*.rx") if item.is_file())
    if not recipes:
        raise ValueError(f"Recipe tree contains no .rx files: {directory}")

    root = normalize_path(path) if path is not None else (directory.name,)
    state = getattr(gateway, "_ingested_recipe_operations", None)
    if state is None:
        state = {}
        gateway._ingested_recipe_operations = state

    wrapped = []
    for recipe in recipes:
        segments = _recipe_segments(directory, recipe)
        operation_path = (*root, *segments)
        key = (recipe, operation_path)
        existing = state.get(key)
        if existing is not None:
            wrapped.append(existing)
            continue

        name = canonical_name(operation_path)
        collision = gateway.ops.resolve(name)
        if collision is not None:
            raise ValueError(f"Recipe ingestion conflicts with existing operation: {name}")

        callable_ = _recipe_callable(gateway, recipe)
        operation = IngestedOperation(
            operation_path,
            callable_,
            source=recipe,
            kind="recipe",
            metadata={
                "recipe": str(recipe),
                "root": directory,
            },
        )
        registered = register_operation(gateway, operation)
        state[key] = registered
        wrapped.append(registered)

    return wrapped
