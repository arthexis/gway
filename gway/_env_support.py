"""Internal helpers for environment configuration handling."""

from __future__ import annotations

import logging
import os
from typing import Dict

__all__ = [
    "get_base_client",
    "get_base_server",
    "load_env",
    "parse_env_file",
]

_LOGGER = logging.getLogger("gway.envs")


def get_base_client() -> str:
    """Return the default client name, falling back to ``guest``.

    The helper prefers :func:`getpass.getuser` but gracefully falls back to
    the ``USER``/``USERNAME`` environment variables before defaulting to
    ``guest``.  Errors raised by :mod:`getpass` are intentionally swallowed so
    the caller never receives an exception during startup.
    """

    try:
        import getpass

        username = getpass.getuser()
        if username:
            return username
    except Exception:  # pragma: no cover - highly platform specific
        pass

    for env_var in ("CLIENT", "USER", "USERNAME"):
        value = os.environ.get(env_var)
        if value:
            return value
    return "guest"


def get_base_server() -> str:
    """Return the default server name, falling back to ``localhost``."""

    try:
        import socket

        hostname = socket.gethostname()
        if hostname:
            return hostname
    except Exception:  # pragma: no cover - highly platform specific
        pass

    return os.environ.get("SERVER") or "localhost"


def parse_env_file(env_file: str) -> Dict[str, str]:
    """Return the key/value pairs contained in ``env_file``.

    Missing files simply return an empty mapping.  Any I/O errors are logged at
    ``WARNING`` level so that environment loading never aborts the process.
    """

    env_vars: Dict[str, str] = {}
    try:
        with open(env_file, "r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, value = line.split("=", 1)
                    env_vars[key.strip()] = value.strip()
    except FileNotFoundError:
        return {}
    except OSError as exc:
        _LOGGER.warning("Failed to read env file %s: %s", env_file, exc)
    return env_vars


def _merge_base_environment(
    env_type: str,
    env_dir: str,
    primary_env: Dict[str, str],
) -> None:
    base_env_name = primary_env.get("BASE_ENV")
    if not base_env_name:
        return

    base_env_file = os.path.join(env_dir, f"{base_env_name.lower()}.env")
    if not os.path.isfile(base_env_file):
        _LOGGER.debug(
            "%s environment '%s' declared BASE_ENV '%s' but file %s does not exist",
            env_type,
            primary_env.get(env_type.upper(), "<unknown>"),
            base_env_name,
            base_env_file,
        )
        return

    for key, value in parse_env_file(base_env_file).items():
        os.environ.setdefault(key, value)


def load_env(env_type: str, name: str, env_root: str) -> None:
    """Load variables for ``env_type``/``name`` from ``env_root``.

    The function mirrors the behaviour of historical :mod:`gway.envs` while
    providing robust error handling so environments are always initialised.
    """

    assert env_type in {"client", "server"}, "env_type must be 'client' or 'server'"

    env_dir = os.path.join(env_root, f"{env_type}s")
    os.makedirs(env_dir, exist_ok=True)

    env_file = os.path.join(env_dir, f"{name.lower()}.env")
    if not os.path.isfile(env_file):
        try:
            open(env_file, "a", encoding="utf-8").close()
        except OSError as exc:
            _LOGGER.warning("Unable to create %s file %s: %s", env_type, env_file, exc)
            return

    primary_env = parse_env_file(env_file)
    _merge_base_environment(env_type, env_dir, primary_env)

    for key, value in primary_env.items():
        os.environ[key] = value

    os.environ[env_type.upper()] = name
