from __future__ import annotations

import sys
from pathlib import Path

import pytest

from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.dispatcher.errors import DispatchError
from gway.project import Project
from gway.recipe import RecipeSession
from gway.registry import Registry


def _session(tmp_path: Path) -> RecipeSession:
    root = tmp_path / "recipe-project"
    root.mkdir()
    (root / "recipe_commands.py").write_text(
        """def named() -> dict[str, str]:
    return {\"customer\": \"cust-1\", \"charger\": \"chg-1\"}


def scalar() -> str:
    return \"alpha\"


def use_named(*, customer: str, charger: str) -> str:
    return f\"{customer}:{charger}\"


def echo(value: str) -> str:
    return value
""",
        encoding="utf-8",
    )
    sys.modules.pop("recipe_commands", None)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    registry.register(
        Project(
            name="demo",
            path=root,
            adapter_type="python",
            adapter_config={"module": "recipe_commands"},
        )
    )
    return RecipeSession(Dispatcher(registry))


def test_mapping_result_supplies_named_options_to_later_statement(tmp_path: Path) -> None:
    session = _session(tmp_path)

    assert session.run(["demo", "named"]) == {
        "customer": "cust-1",
        "charger": "chg-1",
    }
    assert session.run(["demo", "use-named"]) == "cust-1:chg-1"


def test_scalar_result_does_not_feed_positional_across_statements(tmp_path: Path) -> None:
    session = _session(tmp_path)

    assert session.run(["demo", "scalar"]) == "alpha"
    with pytest.raises(SystemExit):
        session.run(["demo", "echo"])


def test_explicit_named_option_overrides_persistent_context(tmp_path: Path) -> None:
    session = _session(tmp_path)

    session.run(["demo", "named"])
    assert (
        session.run(
            ["demo", "use-named", "--customer", "override"],
        )
        == "override:chg-1"
    )


def test_explicit_chain_still_transfers_scalar_positionally(tmp_path: Path) -> None:
    session = _session(tmp_path)

    assert session.run(["demo", "scalar", "-", "demo", "echo"]) == "alpha"


def test_store_publishes_named_values_for_later_statements(tmp_path: Path) -> None:
    session = _session(tmp_path)

    result = session.run(["store", "--customer", "cust-9", "--charger=chg-9"])

    assert result == {"customer": "cust-9", "charger": "chg-9"}
    assert session.context["customer"] == "cust-9"
    assert session.context["charger"] == "chg-9"
    assert session.context["result"] == result
    assert session.run(["demo", "use-named"]) == "cust-9:chg-9"


def test_store_supports_boolean_style_options(tmp_path: Path) -> None:
    session = _session(tmp_path)

    assert session.run(["store", "--enabled", "--no-dry-run"]) == {
        "enabled": True,
        "dry_run": False,
    }


def test_store_resolves_sigils_against_existing_context(tmp_path: Path) -> None:
    session = _session(tmp_path)
    session.run(["demo", "named"])

    assert session.run(["store", "--selected", "[customer]"]) == {
        "selected": "cust-1",
    }
    assert session.context["selected"] == "cust-1"


def test_store_rejects_reserved_result_key(tmp_path: Path) -> None:
    session = _session(tmp_path)

    with pytest.raises(DispatchError, match="reserved context key: result"):
        session.run(["store", "--result", "shadow"])


def test_store_rejects_positional_values(tmp_path: Path) -> None:
    session = _session(tmp_path)

    with pytest.raises(DispatchError, match="named options only"):
        session.run(["store", "value"])


def test_result_replays_latest_captured_result(tmp_path: Path) -> None:
    session = _session(tmp_path)
    expected = session.run(["demo", "named"])

    assert session.run(["result"]) == expected
    assert session.context["result"] == expected


def test_result_can_extract_named_context_with_sigils(tmp_path: Path) -> None:
    session = _session(tmp_path)
    session.run(["demo", "named"])

    assert session.run(["result", "[customer]"]) == "cust-1"
    assert session.context["result"] == "cust-1"


def test_result_is_none_before_any_captured_value(tmp_path: Path) -> None:
    session = _session(tmp_path)

    assert session.run(["result"]) is None
    assert session.context["result"] is None


def test_result_expression_can_feed_explicit_chain(tmp_path: Path) -> None:
    session = _session(tmp_path)
    session.run(["demo", "named"])

    assert (
        session.run(["result", "[customer]", "-", "demo", "echo"])
        == "cust-1"
    )
