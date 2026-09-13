from __future__ import annotations

import errno
import os
import stat
from pathlib import Path

import pytest

from gway import bootstrap
from gway import resume as resume_module
from gway.checkpoint import (
    CheckpointError,
    CheckpointFlags,
    ResumeCheckpoint,
    recipe_identity,
)
from gway.checkpoint_store import (
    _sync_directory,
    checkpoint_directory,
    claim_checkpoint,
    restore_checkpoint,
    write_checkpoint_atomic,
)
from gway.config import GwayPaths
from gway.project import Project
from gway.provenance import ContinuationPoint, ValueProvenance
from gway.recipe import recipe_statements
from gway.registry import Registry, RegistryError


def _checkpoint(recipe: Path) -> ResumeCheckpoint:
    return ResumeCheckpoint(
        recipe=recipe_identity(recipe),
        continuation=ContinuationPoint(
            recipe_path=str(recipe),
            statement_index=1,
            line=1,
            next_statement_index=None,
            next_line=None,
        ),
        flags=CheckpointFlags(),
    )


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are not authoritative on Windows")
def test_checkpoint_storage_is_owner_only_independent_of_umask(tmp_path: Path) -> None:
    recipe = tmp_path / "secure.rx"
    recipe.write_text("reload\n", encoding="utf-8")
    data_dir = tmp_path / "data"

    old_umask = os.umask(0)
    try:
        path = write_checkpoint_atomic(_checkpoint(recipe), data_dir)
    finally:
        os.umask(old_umask)

    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert stat.S_IMODE(checkpoint_directory(data_dir).stat().st_mode) == 0o700


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are not authoritative on Windows")
def test_checkpoint_storage_rejects_insecure_existing_directory(tmp_path: Path) -> None:
    recipe = tmp_path / "secure.rx"
    recipe.write_text("reload\n", encoding="utf-8")
    data_dir = tmp_path / "data"
    directory = checkpoint_directory(data_dir)
    directory.mkdir(parents=True, mode=0o755)
    directory.chmod(0o755)

    with pytest.raises(CheckpointError, match="must not be accessible by group or others"):
        write_checkpoint_atomic(_checkpoint(recipe), data_dir)

    assert stat.S_IMODE(directory.stat().st_mode) == 0o755


def test_resume_error_args_restore_original_invocation(monkeypatch) -> None:
    monkeypatch.setenv(
        "GWAY_RESUME_ORIGINAL_ARGV",
        '["--json","recipe","deploy.rx"]',
    )

    assert bootstrap._resume_error_args(["--resume", "/tmp/checkpoint.json"]) == [
        "--json",
        "recipe",
        "deploy.rx",
    ]
    assert "GWAY_RESUME_ORIGINAL_ARGV" not in os.environ


def test_recipe_statements_canonicalize_relative_path_before_execution(
    tmp_path: Path, monkeypatch
) -> None:
    recipe = tmp_path / "relative.rx"
    recipe.write_text("reload\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    statement = next(recipe_statements(Path("relative.rx")))

    assert statement.path == recipe.resolve()
    assert statement.path.is_absolute()


def test_registry_reserves_reload_project_name_and_alias(tmp_path: Path) -> None:
    registry = Registry(GwayPaths(tmp_path / "config", tmp_path / "data"))

    with pytest.raises(RegistryError, match="reserved GWAY operation: reload"):
        registry.register(
            Project(
                name="reload",
                path=tmp_path / "reload-project",
                adapter_type="python",
                adapter_config={"module": "commands"},
            )
        )

    with pytest.raises(RegistryError, match="reserved GWAY operation: reload"):
        registry.register(
            Project(
                name="demo",
                path=tmp_path / "demo-project",
                adapter_type="python",
                adapter_config={"module": "commands"},
                aliases=("reload",),
            )
        )


def test_checkpoint_claim_is_single_consumer(tmp_path: Path) -> None:
    recipe = tmp_path / "claim.rx"
    recipe.write_text("reload\n", encoding="utf-8")
    original = write_checkpoint_atomic(_checkpoint(recipe), tmp_path / "data")

    claimed = claim_checkpoint(original)

    assert not original.exists()
    assert claimed.exists()
    with pytest.raises(CheckpointError, match="cannot claim checkpoint"):
        claim_checkpoint(original)

    restore_checkpoint(claimed, original)
    assert original.exists()


@pytest.mark.skipif(os.name == "nt", reason="directory fsync is skipped on Windows")
def test_directory_sync_ignores_only_unsupported_errors(tmp_path: Path, monkeypatch) -> None:
    def unsupported(_descriptor: int) -> None:
        raise OSError(errno.EINVAL, "unsupported")

    monkeypatch.setattr("gway.checkpoint_store.os.fsync", unsupported)
    _sync_directory(tmp_path)

    def io_error(_descriptor: int) -> None:
        raise OSError(errno.EIO, "I/O failure")

    monkeypatch.setattr("gway.checkpoint_store.os.fsync", io_error)
    with pytest.raises(CheckpointError, match="cannot sync checkpoint directory"):
        _sync_directory(tmp_path)


def test_checkpoint_detaches_caller_owned_json_state(tmp_path: Path) -> None:
    recipe = tmp_path / "owned.rx"
    recipe.write_text("reload\n", encoding="utf-8")
    context = {"nested": {"values": [1]}}
    previous = {"values": [2]}

    checkpoint = ResumeCheckpoint(
        recipe=recipe_identity(recipe),
        continuation=ContinuationPoint(str(recipe), 1, 1, None, None),
        context=context,
        has_previous_result=True,
        previous_result=previous,
    )
    context["nested"]["values"].append(3)
    previous["values"].append(4)

    assert checkpoint.context == {"nested": {"values": [1]}}
    assert checkpoint.previous_result == {"values": [2]}


def test_checkpoint_rejects_invalid_provenance(tmp_path: Path) -> None:
    recipe = tmp_path / "provenance.rx"
    recipe.write_text("reload\n", encoding="utf-8")
    bad = ValueProvenance(
        frame_id="",
        frame_kind="operation",
        operation="reload",
        tokens=("reload",),
        recipe_path=str(recipe),
        recipe_line=1,
    )

    with pytest.raises(CheckpointError, match="frame_id must be a non-empty string"):
        ResumeCheckpoint(
            recipe=recipe_identity(recipe),
            continuation=ContinuationPoint(str(recipe), 1, 1, None, None),
            context={"result": None},
            context_provenance={"result": bad},
        )


def test_resume_executes_the_same_recipe_snapshot_it_validates(
    tmp_path: Path, monkeypatch
) -> None:
    recipe = tmp_path / "snapshot.rx"
    original_source = "first\nsecond\n"
    recipe.write_text(original_source, encoding="utf-8")
    checkpoint = ResumeCheckpoint(
        recipe=recipe_identity(recipe),
        continuation=ContinuationPoint(str(recipe), 1, 1, 2, 2),
    )

    validate = resume_module._validate_recipe_source

    def validate_then_replace(checkpoint, path, payload, source):
        result = validate(checkpoint, path, payload, source)
        recipe.write_text("first\nchanged\n", encoding="utf-8")
        return result

    captured: dict[str, object] = {}

    def fake_run_recipe_from(recipe_path, session, **kwargs):
        captured["source"] = kwargs["source"]
        return "resumed"

    monkeypatch.setattr(resume_module, "_validate_recipe_source", validate_then_replace)
    monkeypatch.setattr(resume_module, "_run_recipe_from", fake_run_recipe_from)

    assert resume_module.resume_recipe(
        checkpoint,
        object(),  # type: ignore[arg-type]
        runtime=object(),  # type: ignore[arg-type]
    ) == "resumed"
    assert captured["source"] == original_source
