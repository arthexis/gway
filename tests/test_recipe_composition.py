from __future__ import annotations

import sys
from pathlib import Path

from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.explain import explain_scope
from gway.project import Project
from gway.registry import Registry
from gway.runtime import GwayRuntime


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "composition-project"
    root.mkdir()
    (root / "composition_commands.py").write_text(
        """def mapping() -> dict[str, str]:
    return {\"customer\": \"cust-5\", \"charger\": \"chg-5\"}


def echo(value: str) -> str:
    return value


def use_customer(*, customer: str) -> str:
    return customer
""",
        encoding="utf-8",
    )
    sys.modules.pop("composition_commands", None)
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "composition_commands"},
        )
    )
    return Dispatcher(registry)


def test_recipe_final_result_chains_outward(tmp_path: Path) -> None:
    recipe = tmp_path / "outgoing.rx"
    recipe.write_text("demo echo alpha\n", encoding="utf-8")

    result = GwayRuntime(_dispatcher(tmp_path)).execute(
        ["recipe", str(recipe), "-", "demo", "echo"]
    )

    assert result == "alpha"


def test_scalar_chain_input_seeds_only_recipe_result(tmp_path: Path) -> None:
    recipe = tmp_path / "scalar.rx"
    recipe.write_text("result\n", encoding="utf-8")

    result = GwayRuntime(_dispatcher(tmp_path)).execute(
        ["demo", "echo", "alpha", "-", "recipe", str(recipe)]
    )

    assert result == "alpha"


def test_mapping_chain_input_seeds_named_recipe_context(tmp_path: Path) -> None:
    recipe = tmp_path / "mapping.rx"
    recipe.write_text("demo use_customer\n", encoding="utf-8")

    result = GwayRuntime(_dispatcher(tmp_path)).execute(
        ["demo", "mapping", "-", "recipe", str(recipe)]
    )

    assert result == "cust-5"


def test_nested_recipe_inherits_parent_named_context(tmp_path: Path) -> None:
    child = tmp_path / "child.rx"
    child.write_text("demo use_customer\n", encoding="utf-8")
    parent = tmp_path / "parent.rx"
    parent.write_text(f"demo mapping\nrecipe {child}\n", encoding="utf-8")

    result = GwayRuntime(_dispatcher(tmp_path)).execute(["recipe", str(parent)])

    assert result == "cust-5"


def test_child_local_context_does_not_leak_to_parent(tmp_path: Path) -> None:
    recipe = tmp_path / "isolated.rx"
    recipe.write_text("store --temporary secret\ndemo echo done\n", encoding="utf-8")
    context: dict[str, object] = {"parent": "kept"}

    result = GwayRuntime(_dispatcher(tmp_path)).execute(
        ["recipe", str(recipe)], context=context
    )

    assert result == "done"
    assert context["parent"] == "kept"
    assert "temporary" not in context
    assert context["result"] == "done"


def test_child_final_mapping_publishes_back_normally(tmp_path: Path) -> None:
    recipe = tmp_path / "publish.rx"
    recipe.write_text("store --published yes\n", encoding="utf-8")
    context: dict[str, object] = {}

    result = GwayRuntime(_dispatcher(tmp_path)).execute(
        ["recipe", str(recipe)], context=context
    )

    assert result == {"published": "yes"}
    assert context["published"] == "yes"
    assert context["result"] == result


def test_explicit_child_argument_wins_over_inherited_context(tmp_path: Path) -> None:
    recipe = tmp_path / "explicit.rx"
    recipe.write_text("demo use_customer --customer explicit\n", encoding="utf-8")

    result = GwayRuntime(_dispatcher(tmp_path)).execute(
        ["recipe", str(recipe)], context={"customer": "inherited"}
    )

    assert result == "explicit"


def test_recipe_chain_emits_frame_provenance(tmp_path: Path) -> None:
    recipe = tmp_path / "trace.rx"
    recipe.write_text("result\n", encoding="utf-8")
    runtime = GwayRuntime(_dispatcher(tmp_path))

    with explain_scope() as trace:
        assert runtime.execute(
            ["demo", "echo", "alpha", "-", "recipe", str(recipe)]
        ) == "alpha"

    kinds = [step.kind for step in trace]
    assert "recipe.frame.enter" in kinds
    assert "recipe.frame.exit" in kinds


def test_recipe_can_chain_directly_into_another_recipe(tmp_path: Path) -> None:
    first = tmp_path / "first.rx"
    first.write_text("demo echo alpha\n", encoding="utf-8")
    second = tmp_path / "second.rx"
    second.write_text("result\n", encoding="utf-8")

    result = GwayRuntime(_dispatcher(tmp_path)).execute(
        ["recipe", str(first), "-", "recipe", str(second)]
    )

    assert result == "alpha"
