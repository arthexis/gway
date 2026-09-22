from dataclasses import dataclass, field
from pathlib import Path
import sys

import pytest


@pytest.fixture
def recipe_factory(tmp_path):
    """Create .rx recipes and optional same-stem Python companions."""

    def create(name="demo", body="", *, companion=None, root=None):
        root = tmp_path if root is None else Path(root)
        root.mkdir(parents=True, exist_ok=True)
        recipe = root / f"{name}.rx"
        recipe.write_text(body, encoding="utf-8")
        if companion is not None:
            recipe.with_suffix(".py").write_text(companion, encoding="utf-8")
        return recipe

    return create


@dataclass
class RequiredRuntime:
    uv: Path
    python: Path
    sync_calls: list = field(default_factory=list)


@pytest.fixture
def required_runtime(monkeypatch, tmp_path):
    """Stub uv/environment convergence while retaining real companion workers."""
    state = RequiredRuntime(
        uv=tmp_path / "uv",
        python=Path(sys.executable),
    )
    monkeypatch.setattr(
        "gway.recipe.uv.ensure_uv",
        lambda **kwargs: state.uv,
    )

    def sync(environment, executable, requirements):
        state.sync_calls.append(
            (environment, executable, tuple(requirements))
        )
        return state.python

    monkeypatch.setattr(
        "gway.recipe.environment.sync_python_environment",
        sync,
    )
    monkeypatch.setattr(
        "gway.recipe.environment.environment_python",
        lambda environment: state.python,
    )
    return state
