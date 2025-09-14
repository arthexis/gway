from __future__ import annotations

import os
from gway import gw
from gway.envs import parse_env_file, get_base_client


def _client_env_file() -> str:
    """Return path to the current client's .env file."""
    client = os.environ.get("CLIENT") or get_base_client()
    env_dir = os.path.join(gw.base_path, "envs", "clients")
    os.makedirs(env_dir, exist_ok=True)
    return os.path.join(env_dir, f"{client.lower()}.env")


def save(key: str | None = None, value: str | None = None, **kwargs) -> dict[str, str]:
    """Save environment variable(s) to the client .env file.

    Accepts either positional ``key`` and ``value`` or arbitrary ``--key value``
    pairs. Returns the updated environment mapping.
    """
    updates: dict[str, str] = {}
    if key is not None:
        if value is None:
            raise ValueError("A value must be provided when specifying a key")
        updates[key] = value
    updates.update(kwargs)
    if not updates:
        raise ValueError("No variables provided")

    env_file = _client_env_file()
    env_vars: dict[str, str] = {}
    if os.path.isfile(env_file):
        env_vars = {k.upper(): str(v) for k, v in parse_env_file(env_file).items()}

    for k, v in updates.items():
        k_up = k.upper()
        env_vars[k_up] = str(v)
        os.environ[k_up] = str(v)

    with open(env_file, "w") as f:
        for k in sorted(env_vars):
            f.write(f"{k}={env_vars[k]}\n")

    return env_vars
