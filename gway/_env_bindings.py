"""Utilities for resolving environment helper functions."""

from __future__ import annotations

import functools
import importlib
import logging
from types import SimpleNamespace
from typing import Callable

from . import _env_support

__all__ = ["resolve_env_bindings"]

_LOGGER = logging.getLogger("gway.envs")


def _ensure_callable(module: object | None, name: str) -> Callable | None:
    if module is None:
        return None
    candidate = getattr(module, name, None)
    return candidate if callable(candidate) else None


@functools.lru_cache()
def resolve_env_bindings() -> SimpleNamespace:
    """Return the environment helpers, falling back when necessary."""

    module = None
    try:
        module = importlib.import_module("gway.envs")
    except Exception as exc:  # pragma: no cover - import failure is unexpected
        _LOGGER.warning("Unable to import gway.envs: %s", exc)

    load_env = _ensure_callable(module, "load_env")
    get_base_client = _ensure_callable(module, "get_base_client")
    get_base_server = _ensure_callable(module, "get_base_server")

    if load_env is None:
        if module is not None:
            _LOGGER.warning("gway.envs.load_env missing; using internal fallback implementation")
        load_env = _env_support.load_env
        if module is not None:
            setattr(module, "load_env", load_env)

    if get_base_client is None:
        if module is not None:
            _LOGGER.warning(
                "gway.envs.get_base_client missing; using internal fallback implementation"
            )
        get_base_client = _env_support.get_base_client
        if module is not None:
            setattr(module, "get_base_client", get_base_client)

    if get_base_server is None:
        if module is not None:
            _LOGGER.warning(
                "gway.envs.get_base_server missing; using internal fallback implementation"
            )
        get_base_server = _env_support.get_base_server
        if module is not None:
            setattr(module, "get_base_server", get_base_server)

    return SimpleNamespace(
        load_env=load_env,
        get_base_client=get_base_client,
        get_base_server=get_base_server,
    )
