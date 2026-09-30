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


def resolve_tokens(tokens):
    """Resolve the longest sampler recipe prefix from command tokens."""
    values = []
    for token in tokens:
        value = str(getattr(token, "value", token)).strip()
        if not value or value == "-" or value.startswith("--"):
            break
        values.append(value.replace("-", "_"))

    matches = []
    for name in recipes():
        parts = tuple(part.replace("-", "_") for part in name.split("/"))
        if len(parts) <= len(values) and tuple(values[: len(parts)]) == parts:
            matches.append((len(parts), name))
    if not matches:
        return None

    size, name = max(matches, key=lambda item: item[0])
    return resolve(name), size


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


def _module_name(route, *, root_path=None, namespace="sampler"):
    base = root() if root_path is None else Path(root_path).resolve()
    relative = route.relative_to(base)
    prefix = "_gway_" + str(namespace).replace("-", "_").replace(":", "_")
    return prefix + "_" + "_".join(relative.parts)


def load(name, *, root_path=None, namespace="sampler"):
    """Load one sampler-style Python package lazily without registering operations."""
    relative = Path(str(name))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Sampler module name must be a safe relative path")
    base = root() if root_path is None else Path(root_path).resolve()
    route = (base / relative).resolve()
    package = route / "__init__.py"
    if not package.is_file():
        raise FileNotFoundError(f"Sampler module not found: {name}")

    module_name = _module_name(route, root_path=base, namespace=namespace)
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


def _first_class_recipe_entries(root_path):
    """Return public first-class recipe entries for one operation root."""
    base = Path(root_path).expanduser().resolve()
    if not base.is_dir():
        return ()

    entries = []
    names = {}

    def add(name, path):
        canonical = ".".join(
            part.replace("-", "_")
            for part in str(name).replace("/", ".").split(".")
            if part
        )
        previous = names.get(canonical)
        if previous is not None and previous != path:
            raise LookupError(
                f"Ambiguous first-class recipe {canonical!r}: {previous}, {path}"
            )
        names[canonical] = path
        entries.append((canonical, path))

    for recipe in sorted(base.glob("*.rx")):
        if recipe.is_file() and recipe.stem != "__main__":
            add(recipe.stem, recipe.resolve())

    for directory in sorted(path for path in base.iterdir() if path.is_dir()):
        entry = directory / "__main__.rx"
        if not entry.is_file():
            continue
        family = directory.name
        add(family, entry.resolve())
        for child in sorted(directory.glob("*.rx")):
            if not child.is_file() or child.name == "__main__.rx":
                continue
            add(f"{family}.{child.stem}", child.resolve())

    return tuple(entries)


def _register_matching_first_class_recipe(runtime, tokens, root_path, *, route_name):
    """Register the first-class recipe directly named by unresolved tokens."""
    values = _semantic_values(tokens)
    if not values:
        return False

    candidates = {
        name.replace(".", "_"): (name, recipe)
        for name, recipe in _first_class_recipe_entries(root_path)
    }
    for size in range(len(values), 0, -1):
        key = "_".join(values[:size])
        match = candidates.get(key)
        if match is None:
            continue
        name, recipe = match
        from .recipe.operation import register_recipe_operation

        existing = runtime.ops.resolve(name)
        if existing is not None:
            return True
        return (
            register_recipe_operation(
                runtime,
                name,
                recipe,
                route_name=route_name,
                root=root_path,
            )
            is not None
        )
    return False


def _register_first_class_recipes(runtime, root_path, *, route_name):
    """Register eligible recipe entry points once for one operation route."""
    base = Path(root_path).expanduser().resolve()
    discovered = getattr(runtime, "_operation_recipe_routes", None)
    if discovered is None:
        discovered = set()
        runtime._operation_recipe_routes = discovered

    key = (str(route_name), base)
    if key in discovered:
        return False

    from .recipe.operation import register_recipe_operation

    registered = False
    for name, recipe in _first_class_recipe_entries(base):
        wrapped = register_recipe_operation(
            runtime,
            name,
            recipe,
            route_name=route_name,
            root=base,
        )
        registered = registered or wrapped is not None
    discovered.add(key)
    return registered


def _fallback_routes(root_path=None):
    """Return capability packages in deterministic semantic-search order."""
    sampler_root = root() if root_path is None else Path(root_path).resolve()
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


def fallback_routes(tokens, *, root_path=None):
    """Yield capability routes ordered for one unresolved semantic command."""
    values = _semantic_values(tokens)
    routes = _fallback_routes(root_path)
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


def expand_root(runtime, tokens, root_path, *, route_name="root"):
    """Expand first-class recipes or one capability package from an operation root."""
    values = _semantic_values(tokens)
    if not values:
        return False

    base = Path(root_path).expanduser().resolve()
    if _register_matching_first_class_recipe(
        runtime,
        tokens,
        base,
        route_name=route_name,
    ):
        return True

    recipes_registered = _register_first_class_recipes(
        runtime,
        base,
        route_name=route_name,
    )
    if recipes_registered:
        return True
    loaded = getattr(runtime, "_operation_route_loaded", None)
    if loaded is None:
        loaded = set()
        runtime._operation_route_loaded = loaded

    candidates = []
    for relative in fallback_routes(tokens, root_path=base):
        route = (base / relative).resolve()
        key = (str(route_name), route)
        if key not in loaded:
            candidates.append((relative, route, key))

    if not candidates:
        return False

    best_score = _route_score(candidates[0][0], values)
    equally_relevant = [
        relative
        for relative, _, _ in candidates
        if _route_score(relative, values) == best_score
    ]
    if (best_score[0] or best_score[1]) and len(equally_relevant) > 1:
        names = ", ".join(str(route) for route in equally_relevant)
        raise LookupError(
            f"Ambiguous operation-route fallback for {' '.join(values)!r}: {names}"
        )

    relative, route, key = candidates[0]
    module = load(str(relative), root_path=base, namespace=route_name)
    register = getattr(module, "register", None)
    if callable(register):
        registry = runtime.ops._registry
        selected_before = dict(registry.records)
        aliases_before = dict(registry.aliases)
        register(runtime)
        for name, previous in selected_before.items():
            current = registry.records.get(name)
            if current is None or current.callable is previous.callable:
                continue
            history = registry.history.setdefault(name, [])
            if history and history[-1] == previous:
                history.pop()
            history.append(current)
            registry.records[name] = previous
        for alias, canonical in aliases_before.items():
            registry.aliases[alias] = canonical
    loaded.add(key)
    return True


def expand(runtime, tokens):
    """Load exactly one next sampler fallback route after ordinary resolution misses."""
    expanded = expand_root(runtime, tokens, root(), route_name="sampler")
    if expanded:
        loaded = getattr(runtime, "_sampler_routes", None)
        if loaded is None:
            loaded = set()
            runtime._sampler_routes = loaded
        for route_name, route in getattr(runtime, "_operation_route_loaded", set()):
            if route_name == "sampler":
                loaded.add(route)
    return expanded
