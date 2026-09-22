"""Canonical logical identities for GWAY logging sources."""


def _segment(value, label):
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string")
    value = value.strip()
    if not value:
        raise ValueError(f"{label} cannot be empty")
    if "/" in value or "\\" in value:
        raise ValueError(f"{label} must be one logical identity segment")
    return value


def gway_identity():
    """Return the canonical identity for GWAY's own logs."""
    return "gway"


def project_identity(project):
    """Return the canonical aggregate identity for one project."""
    return _segment(project, "project")


def service_identity(project, service):
    """Return the canonical identity for one project service."""
    return f"{project_identity(project)}/{_segment(service, 'service')}"


def recipe_identity(identity):
    """Return the canonical identity for one recipe."""
    return f"recipe/{_segment(identity, 'recipe identity')}"
