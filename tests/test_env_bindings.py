"""Tests for environment helper fallbacks."""

from __future__ import annotations

import importlib
import sys
import types

from gway import _env_bindings
from gway import _env_support


def test_resolve_env_bindings_uses_fallback_when_missing() -> None:
    original_module = sys.modules.pop("gway.envs", None)
    dummy_module = types.ModuleType("gway.envs")
    dummy_module.get_base_client = lambda: "dummy-client"  # type: ignore[attr-defined]
    sys.modules["gway.envs"] = dummy_module

    try:
        _env_bindings.resolve_env_bindings.cache_clear()
        bindings = _env_bindings.resolve_env_bindings()

        assert bindings.load_env is _env_support.load_env
        assert bindings.get_base_client() == "dummy-client"
        assert bindings.get_base_server is _env_support.get_base_server

        env_module = sys.modules["gway.envs"]
        assert getattr(env_module, "load_env") is _env_support.load_env
        assert getattr(env_module, "get_base_server") is _env_support.get_base_server
    finally:
        _env_bindings.resolve_env_bindings.cache_clear()
        if original_module is not None:
            sys.modules["gway.envs"] = original_module
        else:
            sys.modules.pop("gway.envs", None)
        importlib.invalidate_caches()
        import gway.envs as real_envs  # noqa: F401 - ensure real module is restored
        importlib.reload(real_envs)
