from __future__ import annotations

import sys
from pathlib import Path

from gway.config import GwayPaths
from gway.dispatcher import Dispatcher
from gway.project import Project
from gway.recipe import run_recipe
from gway.registry import Registry


def _dispatcher(tmp_path: Path) -> Dispatcher:
    root = tmp_path / "fitness-transfer-project"
    root.mkdir()
    (root / "fitness_transfer_commands.py").write_text(
        """CALLS = []


def scalar() -> str:
    CALLS.append(\"scalar\")
    return \"shard-42\"


def mapping() -> dict[str, str]:
    CALLS.append(\"mapping\")
    return {\"token\": \"tok-7\", \"state_id\": \"state-9\"}


def scalar_ready(shard_id: str) -> bool:
    CALLS.append(f\"scalar_ready:{shard_id}\")
    return shard_id == \"shard-42\"


def no_input_ready() -> bool:
    CALLS.append(\"no_input_ready\")
    return True


def mapping_ready(*, token: str, state_id: str) -> bool:
    CALLS.append(f\"mapping_ready:{token}:{state_id}\")
    return token == \"tok-7\" and state_id == \"state-9\"


def calls() -> list[str]:
    return list(CALLS)
""",
        encoding="utf-8",
    )
    sys.modules.pop("fitness_transfer_commands", None)
    paths = GwayPaths(tmp_path / "config", tmp_path / "data")
    registry = Registry(paths)
    registry.register(
        Project(
            name="fitness-transfer",
            path=root,
            adapter_type="python",
            adapter_config={"module": "fitness_transfer_commands"},
        )
    )
    return Dispatcher(registry)


def test_fitness_consumes_scalar_operation_result(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "scalar.rx"
    path.write_text(
        "fitness-transfer scalar --> fitness-transfer scalar-ready\n",
        encoding="utf-8",
    )

    assert run_recipe(path, dispatcher) == "shard-42"
    assert dispatcher.invoke("fitness-transfer", ("calls",)) == [
        "scalar",
        "scalar_ready:shard-42",
    ]


def test_zero_argument_fitness_omits_scalar_transfer(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "zero.rx"
    path.write_text(
        "fitness-transfer scalar --> fitness-transfer no-input-ready\n",
        encoding="utf-8",
    )

    assert run_recipe(path, dispatcher) == "shard-42"
    assert dispatcher.invoke("fitness-transfer", ("calls",)) == [
        "scalar",
        "no_input_ready",
    ]


def test_fitness_consumes_mapping_keys_from_semantic_context(tmp_path: Path) -> None:
    dispatcher = _dispatcher(tmp_path)
    path = tmp_path / "mapping.rx"
    path.write_text(
        "fitness-transfer mapping --> fitness-transfer mapping-ready\n",
        encoding="utf-8",
    )

    expected = {"token": "tok-7", "state_id": "state-9"}
    assert run_recipe(path, dispatcher) == expected
    assert dispatcher.invoke("fitness-transfer", ("calls",)) == [
        "mapping",
        "mapping_ready:tok-7:state-9",
    ]
