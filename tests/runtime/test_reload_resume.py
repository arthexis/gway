import json

import pytest

from gway import Gateway
from gway.reload import (
    CheckpointState,
    ReloadCheckpoint,
    ReloadError,
    ReloadStore,
    _restore_runtime,
    resume,
    serialize_tokens,
)
from gway.tokens import tokenize


def _handoff_checkpoint(**kwargs):
    return ReloadCheckpoint.create(**kwargs).transition(CheckpointState.HANDOFF)


def _frame(recipe, *statements, pipeline=()):
    return {
        "recipe": str(recipe),
        "pipeline": serialize_tokens(pipeline),
        "statements": [serialize_tokens(tokenize(statement)) for statement in statements],
    }


def test_store_adoption_is_single_consumer(tmp_path):
    store = ReloadStore(tmp_path / "reload")
    checkpoint = _handoff_checkpoint()
    store.save(checkpoint)

    adopted = store.adopt(checkpoint.checkpoint_id)

    assert adopted.state is CheckpointState.ADOPTED
    assert not store.path(checkpoint.checkpoint_id).exists()
    assert store.adopted_path(checkpoint.checkpoint_id).is_file()

    with pytest.raises(ReloadError, match="already claimed"):
        store.adopt(checkpoint.checkpoint_id)


def test_resume_reingests_recipe_companion_and_continues_without_replaying_prefix(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    recipe = tmp_path / "deploy.rx"
    companion = tmp_path / "deploy.py"
    prefix = tmp_path / "prefix.txt"
    resumed = tmp_path / "resumed.txt"

    companion.write_text(
        "from pathlib import Path\n"
        f"_prefix = Path({str(prefix)!r})\n"
        f"_resumed = Path({str(resumed)!r})\n"
        "def before():\n"
        "    _prefix.write_text('before', encoding='utf-8')\n"
        "    return 'before'\n"
        "def after(site):\n"
        "    _resumed.write_text(site, encoding='utf-8')\n"
        "    return site\n",
        encoding="utf-8",
    )
    recipe.write_text(
        "deploy before\n"
        "reload\n"
        "deploy after\n",
        encoding="utf-8",
    )
    prefix.write_text("already-ran", encoding="utf-8")

    store = ReloadStore(tmp_path / "reload")
    checkpoint = _handoff_checkpoint(
        recipe_stack=(str(recipe),),
        frames=(_frame(recipe, "deploy after"),),
        context={"site": "MTY"},
        result="reload-result",
    )
    store.save(checkpoint)

    assert resume(checkpoint.checkpoint_id, store=store) == "MTY"
    assert prefix.read_text(encoding="utf-8") == "already-ran"
    assert resumed.read_text(encoding="utf-8") == "MTY"
    assert not store.adopted_path(checkpoint.checkpoint_id).exists()

    receipt = json.loads(store.history.read_text(encoding="utf-8"))
    assert receipt["outcome"] == "completed"


def test_resume_loads_nested_companions_outer_to_inner(tmp_path, monkeypatch):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    outer = tmp_path / "outer.rx"
    inner = tmp_path / "inner.rx"
    outer_py = tmp_path / "outer.py"
    inner_py = tmp_path / "inner.py"
    marker = tmp_path / "marker.txt"

    outer.write_text("./inner.rx\nouter finish\n", encoding="utf-8")
    inner.write_text("reload\ninner finish\n", encoding="utf-8")
    outer_py.write_text(
        "def finish(value):\n"
        "    return f'outer:{value}'\n",
        encoding="utf-8",
    )
    inner_py.write_text(
        "from pathlib import Path\n"
        f"_marker = Path({str(marker)!r})\n"
        "def finish():\n"
        "    _marker.write_text('inner', encoding='utf-8')\n"
        "    return 'inner'\n",
        encoding="utf-8",
    )

    store = ReloadStore(tmp_path / "reload")
    checkpoint = _handoff_checkpoint(
        recipe_stack=(str(outer), str(inner)),
        frames=(
            _frame(outer, pipeline=tokenize("outer finish")),
            _frame(inner, "inner finish"),
        ),
        result=None,
    )
    store.save(checkpoint)

    assert resume(checkpoint.checkpoint_id, store=store) == "outer:inner"
    assert marker.read_text(encoding="utf-8") == "inner"


def test_resume_adopts_existing_rollback_session_and_can_commit(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    original = Gateway()
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    recipe = tmp_path / "deploy.rx"
    source.write_text("source", encoding="utf-8")
    recipe.write_text("commit deploy\n", encoding="utf-8")

    with original.execution_scope():
        original.copy(str(source), to=str(destination), rollback="deploy")
        checkpoint = _handoff_checkpoint(
            recipe_stack=(str(recipe),),
            frames=(_frame(recipe, "commit deploy"),),
            journal_session_id=original.journal.session_id,
            open_journals=original.journal.open_names(),
        )
        store = ReloadStore(tmp_path / "reload")
        store.save(checkpoint)
        original.suspend_execution(checkpoint)

    assert resume(checkpoint.checkpoint_id, store=store) == "deploy"
    assert destination.read_text(encoding="utf-8") == "source"

    adopted = original.journal.__class__(
        original.journal.root,
        session_id=checkpoint.journal_session_id,
    )
    assert adopted.open_names() == ()


def test_resume_failure_rolls_back_adopted_journal_and_quarantines_checkpoint(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    original = Gateway()
    source = tmp_path / "source.txt"
    destination = tmp_path / "destination.txt"
    recipe = tmp_path / "deploy.rx"
    companion = tmp_path / "deploy.py"
    source.write_text("source", encoding="utf-8")
    companion.write_text(
        "def fail():\n"
        "    raise RuntimeError('after reload failed')\n",
        encoding="utf-8",
    )
    recipe.write_text("deploy fail\n", encoding="utf-8")

    with original.execution_scope():
        original.copy(str(source), to=str(destination), rollback="deploy")
        checkpoint = _handoff_checkpoint(
            recipe_stack=(str(recipe),),
            frames=(_frame(recipe, "deploy fail"),),
            journal_session_id=original.journal.session_id,
            open_journals=original.journal.open_names(),
        )
        store = ReloadStore(tmp_path / "reload")
        store.save(checkpoint)
        original.suspend_execution(checkpoint)

    with pytest.raises(RuntimeError, match="after reload failed"):
        resume(checkpoint.checkpoint_id, store=store)

    assert not destination.exists()
    assert (store.failed / f"{checkpoint.checkpoint_id}.json").is_file()
    receipt = json.loads(store.history.read_text(encoding="utf-8"))
    assert receipt["outcome"] == "failed"


def test_resume_rejects_mismatched_persisted_journals(tmp_path, monkeypatch):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    checkpoint = _handoff_checkpoint(
        journal_session_id="missing-session",
        open_journals=("deploy",),
    )
    store = ReloadStore(tmp_path / "reload")
    store.save(checkpoint)

    with pytest.raises(ReloadError, match="journals do not match"):
        resume(checkpoint.checkpoint_id, store=store)

    assert (store.failed / f"{checkpoint.checkpoint_id}.json").is_file()


def test_resume_preserves_single_quoted_literal_token_semantics(tmp_path, monkeypatch):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    recipe = tmp_path / "literal.rx"
    companion = tmp_path / "literal.py"
    companion.write_text(
        "def echo(value):\n"
        "    return value\n",
        encoding="utf-8",
    )
    recipe.write_text("literal echo '[site]'\n", encoding="utf-8")

    store = ReloadStore(tmp_path / "reload")
    checkpoint = _handoff_checkpoint(
        recipe_stack=(str(recipe),),
        frames=(_frame(recipe, "literal echo '[site]'"),),
        context={"site": "MTY"},
    )
    store.save(checkpoint)

    assert resume(checkpoint.checkpoint_id, store=store) == "[site]"



def test_fresh_resume_discards_context_history_and_subjects_but_keeps_pipeline(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    recipe = tmp_path / "fresh.rx"
    companion = tmp_path / "fresh.py"
    observed = tmp_path / "observed.txt"

    companion.write_text(
        "from pathlib import Path\n"
        f"_observed = Path({str(observed)!r})\n"
        "def consume(value):\n"
        "    _observed.write_text(value, encoding='utf-8')\n"
        "    return value\n"
        "def inspect(runtime=None):\n"
        "    return 'unused'\n",
        encoding="utf-8",
    )
    recipe.write_text("fresh consume\n", encoding="utf-8")

    store = ReloadStore(tmp_path / "reload")
    checkpoint = _handoff_checkpoint(
        mode="fresh",
        recipe_stack=(str(recipe),),
        frames=(_frame(recipe, pipeline=tokenize("fresh consume")),),
        context={},
        result="pipeline-value",
        result_history=(),
        result_subjects={},
    )
    store.save(checkpoint)

    assert resume(checkpoint.checkpoint_id, store=store) == "pipeline-value"
    assert observed.read_text(encoding="utf-8") == "pipeline-value"


def test_fresh_resume_context_does_not_restore_pre_reload_values(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    recipe = tmp_path / "fresh_context.rx"
    companion = tmp_path / "fresh_context.py"
    companion.write_text(
        "def read(site='missing'):\n"
        "    return site\n",
        encoding="utf-8",
    )
    recipe.write_text("fresh_context read\n", encoding="utf-8")

    store = ReloadStore(tmp_path / "reload")
    checkpoint = _handoff_checkpoint(
        mode="fresh",
        recipe_stack=(str(recipe),),
        frames=(_frame(recipe, "fresh_context read"),),
        context={},
        result="old-result",
        result_history=(),
        result_subjects={},
    )
    store.save(checkpoint)

    assert resume(checkpoint.checkpoint_id, store=store) == "missing"



def test_restart_resume_reexecutes_top_level_recipe_from_start(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    recipe = tmp_path / "restart.rx"
    companion = tmp_path / "restart.py"
    marker = tmp_path / "marker.txt"

    companion.write_text(
        "from pathlib import Path\n"
        f"_marker = Path({str(marker)!r})\n"
        "def start(site):\n"
        "    previous = _marker.read_text(encoding='utf-8') if _marker.exists() else ''\n"
        "    _marker.write_text(previous + site, encoding='utf-8')\n"
        "    return site\n",
        encoding="utf-8",
    )
    recipe.write_text("restart start\n", encoding="utf-8")

    store = ReloadStore(tmp_path / "reload")
    checkpoint = _handoff_checkpoint(
        mode="restart",
        recipe_stack=(str(recipe),),
        frames=(
            {
                "recipe": str(recipe),
                "context": {"site": "MTY"},
                "section": None,
            },
        ),
        context={},
        result=None,
        result_history=(),
        result_subjects={},
        journal_session_id=None,
        open_journals=(),
    )
    store.save(checkpoint)

    assert resume(checkpoint.checkpoint_id, store=store) == "MTY"
    assert marker.read_text(encoding="utf-8") == "MTY"


def test_restart_restore_uses_fresh_rollback_session(tmp_path, monkeypatch):
    monkeypatch.setattr("gway.cache.default_root", lambda: tmp_path / "cache")
    checkpoint = ReloadCheckpoint.create(
        mode="restart",
        recipe_stack=(str(tmp_path / "restart.rx"),),
        frames=(),
        journal_session_id=None,
        open_journals=(),
    )

    runtime = _restore_runtime(checkpoint)

    assert runtime.journal.session_id
    assert runtime.journal.open_names() == ()
