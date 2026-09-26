"""Installed sampler recipe resolution."""

from pathlib import Path
import sys
import sysconfig
from importlib.util import module_from_spec, spec_from_file_location

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


def recipes():
    """Return maintained sampler recipe names in deterministic command form."""
    sampler_root = root()
    if not sampler_root.is_dir():
        return ()

    names = set()
    for path in sampler_root.rglob("*.rx"):
        if not path.is_file():
            continue
        relative = path.relative_to(sampler_root)
        if relative.name == "__main__.rx":
            parts = relative.parent.parts
        elif relative.stem == relative.parent.name:
            parts = relative.parent.parts
        else:
            parts = (*relative.parent.parts, relative.stem)
        if parts:
            names.add("/".join(parts))
    return tuple(sorted(names))


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


def _module_name(route):
    return "_gway_sampler_" + "_".join(route.relative_to(root()).parts)


def load(name):
    """Load one sampler Python package lazily without registering its operations."""
    relative = Path(str(name))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Sampler module name must be a safe relative path")
    route = (root() / relative).resolve()
    package = route / "__init__.py"
    if not package.is_file():
        raise FileNotFoundError(f"Sampler module not found: {name}")

    module_name = _module_name(route)
    existing = sys.modules.get(module_name)
    if existing is not None:
        return existing

    spec = spec_from_file_location(
        module_name,
        package,
        submodule_search_locations=[str(route)],
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Unable to load sampler module: {route}")
    module = module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        raise
    return module


def _semantic_values(tokens):
    """Return normalized semantic spellings from one unresolved command."""
    return tuple(
        value
        for token in tokens
        if (value := str(getattr(token, "value", token)).strip().replace("-", "_"))
        and not value.startswith("--")
    )


def _fallback_routes():
    """Return sampler capability packages in deterministic semantic-search order."""
    sampler_root = root()
    if not sampler_root.is_dir():
        return ()

    routes = []
    for package in sampler_root.rglob("__init__.py"):
        route = package.parent
        relative = route.relative_to(sampler_root)
        if not relative.parts:
            continue
        routes.append(relative)
    return tuple(sorted(routes, key=lambda item: (len(item.parts), item.parts)))


def _route_score(route, values):
    """Prefer sampler routes whose semantic path overlaps the unresolved command."""
    normalized = tuple(part.replace("-", "_") for part in route.parts)
    overlap = sum(part in values for part in normalized)
    leaf = normalized[-1] in values
    return (leaf, overlap, -len(normalized))


def fallback_routes(tokens):
    """Yield sampler capability routes ordered for one unresolved semantic command."""
    values = _semantic_values(tokens)
    routes = _fallback_routes()
    return tuple(
        sorted(
            routes,
            key=lambda route: (
                -int(_route_score(route, values)[0]),
                -_route_score(route, values)[1],
                -_route_score(route, values)[2],
                route.parts,
            ),
        )
    )


def expand(runtime, tokens):
    """Load exactly one next sampler fallback route after ordinary resolution misses."""
    values = _semantic_values(tokens)
    if not values:
        return False

    loaded = getattr(runtime, "_sampler_routes", None)
    if loaded is None:
        loaded = set()
        runtime._sampler_routes = loaded

    candidates = []
    for relative in fallback_routes(tokens):
        route = (root() / relative).resolve()
        if route not in loaded:
            candidates.append((relative, route))

    if not candidates:
        return False

    best_score = _route_score(candidates[0][0], values)
    equally_relevant = [
        relative
        for relative, _ in candidates
        if _route_score(relative, values) == best_score
    ]
    if (best_score[0] or best_score[1]) and len(equally_relevant) > 1:
        names = ", ".join(str(route) for route in equally_relevant)
        raise LookupError(
            f"Ambiguous sampler fallback for {' '.join(values)!r}: {names}"
        )

    relative, route = candidates[0]
    module = load(str(relative))
    register = getattr(module, "register", None)
    if callable(register):
        register(runtime)
    loaded.add(route)
    return True
