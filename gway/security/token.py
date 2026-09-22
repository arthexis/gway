"""GWAY command facade for opaque security tokens."""

from .tokens import TokenRegistry as _TokenRegistry


_registry = None


def registry():
    """Return the process-local default token registry."""
    global _registry
    if _registry is None:
        _registry = _TokenRegistry()
    return _registry


def create(name, *scopes, expires=None):
    """Issue a token and return its bearer secret exactly once.

    Args:
        name: Stable token subject/name.
        scopes: Named scopes to bind.
        expires: Optional timezone-aware ISO-8601 expiry timestamp.
    """
    return registry().create(name, scopes=scopes, expires_at=expires).bearer


def show(name):
    """Return safe metadata for one named token."""
    return registry().require(name)


def list():
    """Return safe metadata for all named tokens."""
    return registry().all()


def delete(name):
    """Permanently revoke and remove one named token."""
    return registry().remove(name)


def disable(name):
    """Disable one token without removing its scope bindings."""
    return registry().disable(name)


def enable(name):
    """Re-enable one disabled token."""
    return registry().enable(name)


def set(name, *scopes):
    """Replace the complete named-scope binding set for one token."""
    return registry().replace_scopes(name, scopes)


def bind(name, scope):
    """Bind one additional scope to a token."""
    return registry().bind(name, scope)


def unbind(name, scope):
    """Remove one scope binding from a token."""
    return registry().unbind(name, scope)
