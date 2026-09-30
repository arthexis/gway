from gway.tailing import iter_events, terminal


def test_tail_emits_only_changed_snapshots_and_stops_for_completed_checks():
    values = iter(
        [
            [{"name": "tests", "status": "queued", "conclusion": None}],
            [{"name": "tests", "status": "queued", "conclusion": None}],
            [{"name": "tests", "status": "in_progress", "conclusion": None}],
            [{"name": "tests", "status": "completed", "conclusion": "success"}],
        ]
    )

    events = list(
        iter_events(
            lambda: next(values),
            "github checks arthexis/gway abc123",
            interval=0,
        )
    )

    assert [event["kind"] for event in events] == [
        "update",
        "update",
        "complete",
    ]
    assert [event["sequence"] for event in events] == [1, 2, 3]
    assert events[-1]["terminal"] is True
    assert events[-1]["value"][0]["conclusion"] == "success"


def test_tail_forwards_native_iterators():
    events = list(
        iter_events(
            lambda: iter(["one", "two"]),
            "log follow gway",
            interval=0,
        )
    )

    assert [event["value"] for event in events] == ["one", "two", None]
    assert events[-1]["kind"] == "complete"
    assert events[-1]["terminal"] is True


def test_tail_timeout_is_terminal_for_non_terminal_operations():
    clocks = iter([0.0, 0.0, 1.0])

    events = list(
        iter_events(
            lambda: {"health": "ok"},
            "survey",
            interval=0,
            timeout=0.5,
            clock=lambda: next(clocks),
        )
    )

    assert [event["kind"] for event in events] == ["update", "timeout"]
    assert events[-1]["terminal"] is True


def test_github_terminal_detection_is_limited_to_status_operations():
    assert terminal(
        "github run arthexis/gway 42",
        {"status": "completed", "conclusion": "success"},
    )
    assert not terminal("survey", {"status": "ok"})
