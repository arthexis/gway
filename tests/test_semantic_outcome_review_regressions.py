from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gway import sigils as gway_sigils
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.explain import explain_scope
from gway.outcome import SemanticFailure
from gway.project import Project
from gway.registry import Registry
from gway.runtime import GwayRuntime


def _registry(tmp_path: Path) -> Registry:
    root = tmp_path / "semantic-provider"
    root.mkdir()
    (root / "semantic_provider.py").write_text(
        """from gway import failure, success


def semantic_ok():
    return success("ok")


def semantic_fail():
    return failure("bad", message="provider blocked")
""",
        encoding="utf-8",
    )
    sys.modules.pop("semantic_provider", None)
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "semantic_provider"},
        )
    )
    return registry


def test_direct_sigil_callable_unwraps_success_outcome(tmp_path: Path, monkeypatch) -> None:
    registry = _registry(tmp_path)
    monkeypatch.setattr(gway_sigils, "_SIGILS_SUPPORTS_PROVIDER_CALLS", True)
    context = gway_sigils.gway_context(registry=registry)

    command = context["demo"].resolve("semantic-ok")

    assert command() == "ok"


def test_direct_sigil_callable_raises_semantic_failure(tmp_path: Path, monkeypatch) -> None:
    registry = _registry(tmp_path)
    monkeypatch.setattr(gway_sigils, "_SIGILS_SUPPORTS_PROVIDER_CALLS", True)
    context = gway_sigils.gway_context(registry=registry)

    command = context["demo"].resolve("semantic-fail")

    with pytest.raises(SemanticFailure, match="provider blocked"):
        command()


def test_successful_runtime_outcome_keeps_operation_provenance(tmp_path: Path) -> None:
    runtime = GwayRuntime(Dispatcher(_registry(tmp_path)))

    with explain_scope() as trace:
        assert runtime.execute(["demo", "semantic_ok"]) == "ok"

    event = next(step for step in trace if step.kind == "runtime.operation.outcome")
    assert event.data["success"] is True
    assert event.data["result"] == "ok"
    assert event.data["provenance"]["operation"] == "demo"


def test_direct_dispatcher_still_resolves_outcome_contract(tmp_path: Path) -> None:
    dispatcher = Dispatcher(_registry(tmp_path))

    assert dispatcher.run("demo", ["semantic_ok"]) == "ok"
    with pytest.raises(SemanticFailure, match="provider blocked"):
        dispatcher.run("demo", ["semantic_fail"])
