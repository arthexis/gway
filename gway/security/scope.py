"""GWAY command facade for named security scopes."""

from pathlib import Path

try:
    import tomllib as _toml
except ModuleNotFoundError:
    import tomli as _toml

from .scopes import ScopeRegistry as _ScopeRegistry


_registry = None


def registry():
    """Return the process-local default scope registry."""
    global _registry
    if _registry is None:
        _registry = _ScopeRegistry()
    return _registry


def create(name):
    """Create an empty named security scope."""
    return registry().create(name)


def show(name, *, mutate=False):
    """Return one named security scope."""
    return registry().require(name)


def list(*, mutate=False):
    """Return all named security scopes."""
    return registry().all()


def delete(name):
    """Delete one named security scope."""
    return registry().remove(name)


def set(name, *operations, environment=None):
    """Replace one scope using operation grants and optional environment names."""
    if environment is None:
        environment_values = ()
    elif isinstance(environment, str):
        environment_values = tuple(
            item.strip() for item in environment.split(",") if item.strip()
        )
    else:
        environment_values = tuple(environment)
    return registry().replace(
        name,
        operations=operations,
        environment=environment_values,
    )


def resolve(*names, mutate=False):
    """Return the union of named security scopes."""
    return registry().resolve(names)



def apply(path):
    """Apply scope definitions from a TOML file transactionally."""
    path = Path(path).expanduser()
    with path.open("rb") as stream:
        document = _toml.load(stream)
    scopes = document.get("scopes")
    if not isinstance(scopes, dict):
        raise ValueError("scope TOML requires a [scopes] table")
    return registry().replace_many(scopes)


def _toml_string(value):
    value = str(value)
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def export(to=None):
    """Export all scopes as stable TOML, optionally writing to a file."""
    lines = []
    for scope in registry().all():
        lines.append(f"[scopes.{_toml_string(scope.name)}]")
        operations = ", ".join(_toml_string(value) for value in sorted(scope.operations))
        environment = ", ".join(
            _toml_string(value) for value in sorted(scope.environment)
        )
        lines.append(f"operations = [{operations}]")
        lines.append(f"environment = [{environment}]")
        lines.append("")
    rendered = "\n".join(lines)
    if to is None:
        return rendered
    path = Path(to).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered, encoding="utf-8")
    return str(path)
