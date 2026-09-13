from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gway.cli import main
from gway.config import GwayPaths
from gway.dispatcher import Dispatcher, DispatchError
from gway.explain import explain_scope
from gway.project import Project
from gway.registry import Registry
from gway.runtime import GwayRuntime


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "parameter-project"
    root.mkdir()
    (root / "parameter_commands.py").write_text(
        """def mapping():
    return {"customer": "incoming", "device_id": "incoming-device"}


def echo(value):
    return value


def use_customer(*, customer):
    return customer


def use_device(*, device_id):
    return device_id


def combine(*, customer, device_id):
    return f"{customer}:{device_id}"
""",
        encoding="utf-8",
    )
    sys.modules.pop("parameter_commands", None)
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "parameter_commands"},
        )
    )
    return Dispatcher(registry)


def test_explicit_recipe_parameter_seeds_named_context(tmp_path: Path) -> None:
    recipe = tmp_path / "customer.rx"
    recipe.write_text("demo use_customer\n", encoding="utf-8")

    result = GwayRuntime(_dispatcher(tmp_path)).execute(
        ["recipe", str(recipe), "--customer", "explicit"]
    )

    assert result == "explicit"


def test_recipe_parameter_supports_equals_and_dash_normalization(tmp_path: Path) -> None:
    recipe = tmp_path / "device.rx"
    recipe.write_text("demo use_device\n", encoding="utf-8")

    result = GwayRuntime(_dispatcher(tmp_path)).execute(
        ["recipe", str(recipe), "--device-id=dev-9"]
    )

    assert result == "dev-9"


def test_explicit_parameter_wins_over_incoming_and_inherited_context(tmp_path: Path) -> None:
    recipe = tmp_path / "precedence.rx"
    recipe.write_text("demo combine\n", encoding="utf-8")
    runtime = GwayRuntime(_dispatcher(tmp_path))

    result = runtime.execute(
        [
            "demo",
            "mapping",
            "-",
            "recipe",
            str(recipe),
            "--customer",
            "explicit",
            "--device-id",
            "explicit-device",
        ],
        context={"customer": "inherited", "device_id": "inherited-device"},
    )

    assert result == "explicit:explicit-device"


def test_nested_recipe_parameters_do_not_leak_back_to_parent(tmp_path: Path) -> None:
    child = tmp_path / "child.rx"
    child.write_text("demo use_customer\n", encoding="utf-8")
    parent = tmp_path / "parent.rx"
    parent.write_text(
        f"recipe {child} --customer child\ndemo use_customer\n",
        encoding="utf-8",
    )

    result = GwayRuntime(_dispatcher(tmp_path)).execute(
        ["recipe", str(parent)],
        context={"customer": "parent"},
    )

    assert result == "parent"


def test_top_level_cli_routes_recipe_parameters_through_runtime(
    tmp_path: Path,
    capsys,
) -> None:
    recipe = tmp_path / "cli.rx"
    recipe.write_text("demo use_customer\n", encoding="utf-8")
    dispatcher = _dispatcher(tmp_path)

    assert main(
        ["recipe", str(recipe), "--customer", "cli-value"],
        dispatcher=dispatcher,
    ) == 0

    assert capsys.readouterr().out.strip() == "cli-value"


def test_well_formed_unused_parameter_is_allowed_without_recipe_schema(tmp_path: Path) -> None:
    recipe = tmp_path / "unused.rx"
    recipe.write_text("demo echo ok\n", encoding="utf-8")

    result = GwayRuntime(_dispatcher(tmp_path)).execute(
        ["recipe", str(recipe), "--future-option", "value"]
    )

    assert result == "ok"


def test_duplicate_parameter_names_after_normalization_are_rejected(tmp_path: Path) -> None:
    recipe = tmp_path / "duplicate.rx"
    recipe.write_text("demo echo ok\n", encoding="utf-8")

    with pytest.raises(DispatchError, match="duplicate recipe parameter"):
        GwayRuntime(_dispatcher(tmp_path)).execute(
            [
                "recipe",
                str(recipe),
                "--device-id",
                "one",
                "--device_id",
                "two",
            ]
        )


def test_reserved_result_parameter_is_rejected(tmp_path: Path) -> None:
    recipe = tmp_path / "reserved.rx"
    recipe.write_text("demo echo ok\n", encoding="utf-8")

    with pytest.raises(DispatchError, match="reserved by GWAY"):
        GwayRuntime(_dispatcher(tmp_path)).execute(
            ["recipe", str(recipe), "--result", "spoofed"]
        )


def test_parameter_requires_value(tmp_path: Path) -> None:
    recipe = tmp_path / "missing.rx"
    recipe.write_text("demo echo ok\n", encoding="utf-8")

    with pytest.raises(DispatchError, match="requires a value"):
        GwayRuntime(_dispatcher(tmp_path)).execute(
            ["recipe", str(recipe), "--customer"]
        )


def test_dash_prefixed_recipe_path_still_supports_parameters(
    tmp_path: Path,
    monkeypatch,
) -> None:
    recipe = tmp_path / "-parameter.rx"
    recipe.write_text("demo use_customer\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    result = GwayRuntime(_dispatcher(tmp_path)).execute(
        ["recipe", "--", "-parameter.rx", "--customer", "literal-path"]
    )

    assert result == "literal-path"


def test_explain_records_explicit_parameter_origin_and_recipe_provenance(tmp_path: Path) -> None:
    recipe = tmp_path / "explain.rx"
    recipe.write_text("demo use_customer\n", encoding="utf-8")
    runtime = GwayRuntime(_dispatcher(tmp_path))

    with explain_scope() as trace:
        assert runtime.execute(
            ["recipe", str(recipe), "--customer", "explained"]
        ) == "explained"

    event = next(step for step in trace if step.kind == "recipe.parameters")
    assert event.data["origin"] == "explicit"
    assert event.data["parameters"] == {"customer": "explained"}
    assert event.data["provenance"]["frame_kind"] == "recipe"
    assert event.data["provenance"]["recipe_path"] == str(recipe)
