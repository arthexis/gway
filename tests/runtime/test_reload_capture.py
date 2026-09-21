import pytest

from gway.reload import ReloadError, capture_reload_checkpoint


def _values(serialized):
    return [item["value"] for item in serialized]


def _statement_values(serialized_statements):
    return [[item["value"] for item in statement] for statement in serialized_statements]


def test_capture_records_only_statements_after_current_reload_point(gateway, tmp_path):
    captured = []

    def before():
        return "before"

    def capture():
        captured.append(capture_reload_checkpoint(gateway, timeout=12))
        return "captured"

    def after():
        return "after"

    gateway.before = gateway.wrap("before", before)
    gateway.capture = gateway.wrap("capture", capture)
    gateway.after = gateway.wrap("after", after)

    recipe = tmp_path / "deploy.rx"
    recipe.write_text(
        "before\n"
        "capture\n"
        "after\n",
        encoding="utf-8",
    )

    assert gateway(recipe) == "after"
    checkpoint = captured[0]
    frame = checkpoint.frames[0]

    assert frame["pipeline"] == []
    assert _statement_values(frame["statements"]) == [["after"]]
    assert checkpoint.result == "before"
    assert checkpoint.recipe_stack == (str(recipe.resolve()),)
    assert checkpoint.timeout == 12


def test_capture_records_only_pipeline_tail_after_current_stage(gateway, tmp_path):
    captured = []

    def before():
        return "before"

    def capture(value):
        captured.append(capture_reload_checkpoint(gateway))
        return value

    def after(value):
        return f"after:{value}"

    gateway.before = gateway.wrap("before", before)
    gateway.capture = gateway.wrap("capture", capture)
    gateway.after = gateway.wrap("after", after)

    recipe = tmp_path / "pipeline.rx"
    recipe.write_text("before - capture - after\n", encoding="utf-8")

    assert gateway(recipe) == "after:before"
    checkpoint = captured[0]
    frame = checkpoint.frames[0]

    assert _values(frame["pipeline"]) == ["after"]
    assert frame["statements"] == []
    assert checkpoint.result == "before"


def test_capture_preserves_outer_and_inner_continuations(gateway, tmp_path):
    captured = []

    def capture():
        captured.append(capture_reload_checkpoint(gateway))
        return "inner"

    def outer_after(value):
        return f"outer:{value}"

    def outer_later():
        return "later"

    gateway.capture = gateway.wrap("capture", capture)
    gateway.outer_after = gateway.wrap("outer_after", outer_after)
    gateway.outer_later = gateway.wrap("outer_later", outer_later)

    inner = tmp_path / "inner.rx"
    outer = tmp_path / "outer.rx"
    inner.write_text(
        "capture\n"
        "clear\n",
        encoding="utf-8",
    )
    outer.write_text(
        "./inner.rx - outer after\n"
        "outer later\n",
        encoding="utf-8",
    )

    assert gateway(outer) == "later"
    checkpoint = captured[0]

    assert checkpoint.recipe_stack == (
        str(outer.resolve()),
        str(inner.resolve()),
    )
    outer_frame, inner_frame = checkpoint.frames
    assert _values(outer_frame["pipeline"]) == ["outer", "after"]
    assert _statement_values(outer_frame["statements"]) == [["outer", "later"]]
    assert inner_frame["pipeline"] == []
    assert _statement_values(inner_frame["statements"]) == [["clear"]]


def test_capture_preserves_quote_provenance_in_remaining_continuation(
    gateway,
    tmp_path,
):
    captured = []

    def capture():
        captured.append(capture_reload_checkpoint(gateway))
        return "ok"

    def echo(value):
        return value

    gateway.capture = gateway.wrap("capture", capture)
    gateway.echo = gateway.wrap("echo", echo)
    gateway.context["site"] = "MTY"

    recipe = tmp_path / "quoted.rx"
    recipe.write_text(
        "capture\n"
        "echo '[site]'\n",
        encoding="utf-8",
    )

    assert gateway(recipe) == "[site]"
    statement = captured[0].frames[0]["statements"][0]

    assert [item["value"] for item in statement] == ["echo", "[site]"]
    assert statement[1]["quote"] == "single"


def test_capture_includes_semantic_history_flags_and_rollback_identity(
    gateway,
    rollback_paths,
    tmp_path,
):
    source, destination = rollback_paths
    captured = []

    def produce():
        return {"status": "ready"}

    def capture():
        captured.append(capture_reload_checkpoint(gateway, when="changed"))
        return "captured"

    gateway.produce = gateway.wrap("produce_status", produce)
    gateway.capture = gateway.wrap("capture", capture)

    recipe = tmp_path / "state.rx"
    recipe.write_text(
        f"copy {source} --to {destination} --rollback deploy\n"
        "produce\n"
        "capture\n"
        "commit deploy\n",
        encoding="utf-8",
    )

    assert gateway(recipe) == "deploy"
    checkpoint = captured[0]

    assert checkpoint.when == "changed"
    assert checkpoint.open_journals == ("deploy",)
    assert checkpoint.journal_session_id
    assert checkpoint.result == {"status": "ready"}
    assert checkpoint.result_history[-1] == {"status": "ready"}
    assert checkpoint.result_subjects["status"] == {"status": "ready"}
    assert checkpoint.flags["verbose"] is False
    assert checkpoint.flags["silent"] is False


def test_capture_requires_active_recipe(gateway):
    with pytest.raises(ReloadError, match="active recipe"):
        capture_reload_checkpoint(gateway)
