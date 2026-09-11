from __future__ import annotations

from gway.explain import ExplainStep, current_trace, explain_scope, record, render_trace


def test_explain_scope_records_and_resets() -> None:
    assert current_trace() == ()

    with explain_scope() as trace:
        record("command.resolve", "resolved managed command", requested=["echo"], selected=["echo"])
        assert current_trace() == tuple(trace)
        assert trace == [
            ExplainStep(
                kind="command.resolve",
                message="resolved managed command",
                data={"requested": ["echo"], "selected": ["echo"]},
            )
        ]

    assert current_trace() == ()


def test_disabled_scope_is_a_noop() -> None:
    with explain_scope(enabled=False) as trace:
        record("ignored", "not recorded")
        assert trace == []
        assert current_trace() == ()


def test_nested_scope_restores_outer_trace() -> None:
    with explain_scope() as outer:
        record("outer", "before")
        with explain_scope() as inner:
            record("inner", "only")
            assert [step.kind for step in inner] == ["inner"]
        record("outer", "after")
        assert [step.kind for step in outer] == ["outer", "outer"]


def test_render_trace_is_stable_plain_text() -> None:
    steps = [
        ExplainStep(
            kind="adapter.select",
            message="selected project adapter",
            data={"project": "demo", "adapter": "python"},
        )
    ]

    assert render_trace(steps) == (
        "Explain:\n"
        "  adapter.select: selected project adapter (project=demo, adapter=python)"
    )
