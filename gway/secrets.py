"""Generic sensitive-file storage backend for physical bindings."""

from pathlib import Path

from .environment import process_environment


DEFAULT_SECRETS_ROOT = Path("/etc/gway/secrets")
SECRETS_ROOT_ENVIRONMENT = "GWAY_SECRETS_DIR"


def root():
    """Return the configured secrets root."""
    configured = process_environment.get(SECRETS_ROOT_ENVIRONMENT, "")
    configured = str(configured).strip()
    return Path(configured).expanduser() if configured else DEFAULT_SECRETS_ROOT


def path(*parts):
    """Return one path inside the configured secrets root."""
    relative = Path(*map(str, parts))
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("secret binding path must stay inside the secrets root")
    return root().joinpath(relative)


def read(*parts):
    """Read one optional UTF-8 secret value.

    Missing or unreadable secret files behave like unresolved optional bindings.
    """
    target = path(*parts)
    try:
        return True, target.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, PermissionError, OSError):
        return False, None
