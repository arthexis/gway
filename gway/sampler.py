"""Installed sampler recipe resolution."""

from pathlib import Path
import sysconfig

from .recipe import execute_recipe


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


def expand(runtime, tokens):
    """Lazily load one sampler fallback route for an unresolved semantic command."""
    values = [
        str(getattr(token, "value", token)).replace("-", "_")
        for token in tokens
        if str(getattr(token, "value", token))
    ]
    if not values:
        return False

    subject = values[1] if len(values) >= 2 else values[0]
    loaded = getattr(runtime, "_sampler_routes", None)
    if loaded is None:
        loaded = set()
        runtime._sampler_routes = loaded

    candidates = []
    sampler_root = root()
    if not sampler_root.is_dir():
        return False
    for semantic_root in sorted(item for item in sampler_root.iterdir() if item.is_dir()):
        route = semantic_root / subject
        companion = route / "__main__.py"
        if companion.is_file():
            candidates.append((semantic_root.name, route, companion))

    if len(candidates) > 1:
        names = ", ".join(name for name, _, _ in candidates)
        raise LookupError(
            f"Ambiguous sampler fallback for {subject!r}: {names}"
        )
    if not candidates:
        return False

    _, route, companion = candidates[0]
    key = route.resolve()
    if key in loaded:
        return False

    from importlib.util import module_from_spec, spec_from_file_location

    module_name = f"_gway_sampler_{route.parent.name}_{route.name}"
    spec = spec_from_file_location(module_name, companion)
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load sampler route: {route}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    register = getattr(module, "register", None)
    if not callable(register):
        raise TypeError(f"Sampler route has no register(runtime): {route}")
    register(runtime)
    loaded.add(key)
    return True
