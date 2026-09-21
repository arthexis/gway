"""Installed recipe bundles shipped with Gway."""

from pathlib import Path

from .recipes import execute_recipe


_ROOT = Path(__file__).resolve().parent / "bundled"


def resolve(name):
    """Resolve one bundled recipe package or explicit recipe name."""
    relative = Path(str(name))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Bundled recipe name must be a safe relative path")

    target = _ROOT / relative
    candidates = []
    if target.suffix == ".rx":
        candidates.append(target)
    else:
        candidates.extend(
            (
                target.with_suffix(".rx"),
                target / f"{target.name}.rx",
                target / "__main__.rx",
            )
        )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(f"Bundled recipe not found: {name}")


def run(runtime, recipe_name, **context):
    """Execute one installed Gway recipe bundle."""
    path = resolve(recipe_name)
    _, result = execute_recipe(runtime, path, context=context)
    return result
