"""GWAY command facade for named security scopes."""

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


def show(name):
    """Return one named security scope."""
    return registry().require(name)


def list():
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


def resolve(*names):
    """Return the union of named security scopes."""
    return registry().resolve(names)
