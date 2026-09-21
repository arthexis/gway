"""Installed sampler recipe resolution."""

from pathlib import Path
import sysconfig

from .recipes import execute_recipe


def _source_root():
    """Return the repository sampler root when running from a source checkout."""
    root = Path(__file__).resolve().parents[1] / "sampler"
    return root if root.is_dir() else None


def _installed_root():
    """Return sampler data installed with the active Python environment."""
    return Path(sysconfig.get_path("data")) / "share" / "gway" / "sampler"


def root():
    """Return the active sampler root, preferring the source checkout."""
    source = _source_root()
    if source is not None:
        return source
    return _installed_root()


def resolve(name):
    """Resolve one sampler recipe package or explicit recipe name."""
    relative = Path(str(name))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Sampler recipe name must be a safe relative path")

    target = root() / relative
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
    raise FileNotFoundError(f"Sampler recipe not found: {name}")


def run(runtime, recipe_name, **context):
    """Execute one sampler recipe."""
    path = resolve(recipe_name)
    _, result = execute_recipe(runtime, path, context=context)
    return result
