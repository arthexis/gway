import pytest

from gway import Gateway
from gway.authorization import AuthorizationError


def test_observe_returns_success_envelope_and_forces_no_mutate():
    gateway = Gateway()
    seen = {}

    def inspect(*, mutate=False):
        seen["mutate"] = mutate
        return {"ok": True}

    gateway.wrap("inspect", inspect)

    result = gateway("observe inspect")

    assert result == {
        "status": "ok",
        "available": True,
        "result": {"ok": True},
        "error": None,
    }
    assert seen["mutate"] is False
    assert gateway.ops.resolve("observe").mutates is False


def test_observe_marks_missing_operation_unavailable():
    gateway = Gateway()

    result = gateway("observe definitely missing")

    assert result["status"] == "unavailable"
    assert result["available"] is False
    assert result["result"] is None
    assert result["error"]["type"] in {"OperationLookupError", "LookupError"}


def test_observe_marks_runtime_failure_as_error_without_hiding_type():
    gateway = Gateway()

    def fail(*, mutate=False):
        raise ConnectionError("offline")

    gateway.wrap("fail", fail)

    result = gateway("observe fail")

    assert result == {
        "status": "error",
        "available": True,
        "result": None,
        "error": {
            "type": "ConnectionError",
            "message": "offline",
        },
    }


def test_observe_blocks_mutating_operation_before_side_effect():
    gateway = Gateway()
    calls = []

    def change():
        calls.append("changed")

    gateway.wrap("change", change)

    result = gateway("observe change")

    assert result["status"] == "blocked"
    assert result["available"] is False
    assert calls == []


def test_observe_reenters_external_authority_for_observed_command():
    gateway = Gateway()
    gateway.wrap("visible", lambda *, mutate=False: "ok")
    gateway.wrap("hidden", lambda *, mutate=False: "secret")

    with gateway.authorized(operations={"observe", "visible"}):
        assert gateway("observe visible")["status"] == "ok"
        denied = gateway("observe hidden")

    assert denied["status"] == "unauthorized"
    assert denied["available"] is False
    assert denied["error"]["type"] == "AuthorizationError"


def test_observe_does_not_weaken_direct_authorization_behavior():
    gateway = Gateway()
    gateway.wrap("hidden", lambda *, mutate=False: "secret")

    with gateway.authorized(operations={"observe"}):
        with pytest.raises(AuthorizationError):
            gateway("hidden")


def test_observed_operation_remains_strict_when_called_directly():
    gateway = Gateway()

    def fail(*, mutate=False):
        raise ConnectionError("offline")

    gateway.wrap("fail", fail)

    with pytest.raises(ConnectionError, match="offline"):
        gateway("fail")


def test_observe_double_dash_preserves_nested_flags_and_section():
    gateway = Gateway()
    seen = {}

    def inspect(target, *, detail=False, limit=0, mutate=False):
        seen.update(
            target=target,
            detail=detail,
            limit=limit,
            mutate=mutate,
        )
        return {"target": target}

    gateway.wrap("inspect", inspect)

    result = gateway(
        "observe --section probe -- inspect charger --detail --limit 3"
    )

    assert result["probe"]["status"] == "ok"
    assert result["probe"]["result"] == {"target": "charger"}
    assert seen == {
        "target": "charger",
        "detail": True,
        "limit": 3,
        "mutate": False,
    }


def test_observe_double_dash_preserves_nested_pipeline():
    gateway = Gateway()
    gateway.wrap("first", lambda *, mutate=False: "one")
    gateway.wrap("second", lambda value, *, mutate=False: f"{value}:two")

    result = gateway("observe -- first - second")

    assert result["status"] == "ok"
    assert result["result"] == "one:two"


def test_observation_collect_omits_unauthorized_but_keeps_unavailable():
    gateway = Gateway()
    gateway.context.update(
        {
            "visible": {
                "status": "ok",
                "available": True,
                "result": {"ready": True},
                "error": None,
            },
            "hidden": {
                "status": "unauthorized",
                "available": False,
                "result": None,
                "error": {"type": "AuthorizationError", "message": "denied"},
            },
            "optional": {
                "status": "unavailable",
                "available": False,
                "result": None,
                "error": {"type": "LookupError", "message": "missing"},
            },
        }
    )

    result = gateway("observation collect visible hidden optional")

    assert "hidden" not in result
    assert result["visible"]["status"] == "ok"
    assert result["optional"]["status"] == "unavailable"
    assert result["health"]["status"] == "ok"
    assert result["health"]["sections"] == {
        "visible": "ok",
        "optional": "unavailable",
    }
    assert isinstance(result["cursor"], str)
    assert result["cursor"]


def test_observation_collect_only_filters_visible_sections_and_health():
    gateway = Gateway()
    gateway.context.update(
        {
            "node": {
                "status": "ok",
                "available": True,
                "result": {"role": "control"},
                "error": None,
            },
            "wire": {
                "status": "error",
                "available": True,
                "result": None,
                "error": {"type": "ConnectionError", "message": "offline"},
            },
        }
    )

    result = gateway("observation collect node wire --only node")

    assert set(result) == {"node", "health", "changed_at", "cursor"}
    assert result["health"]["status"] == "ok"
    assert result["health"]["sections"] == {"node": "ok"}


def test_observation_collect_except_filters_sections_before_health():
    gateway = Gateway()
    gateway.context.update(
        {
            "node": {
                "status": "ok",
                "available": True,
                "result": {},
                "error": None,
            },
            "wire": {
                "status": "error",
                "available": True,
                "result": None,
                "error": {"type": "ConnectionError", "message": "offline"},
            },
        }
    )

    result = gateway("observation collect node wire --except wire")

    assert "wire" not in result
    assert result["health"]["status"] == "ok"
    assert result["health"]["sections"] == {"node": "ok"}


def test_observation_collect_rejects_only_and_except_together():
    gateway = Gateway()

    with pytest.raises(ValueError, match="only one of --only or --except"):
        gateway("observation collect node wire --only node --except wire")


def test_observation_collect_rejects_unknown_section():
    gateway = Gateway()

    with pytest.raises(ValueError, match="Unknown observation section"):
        gateway("observation collect node wire --only mystery")


def test_observation_collect_problems_keeps_failures_and_nonempty_error_logs():
    gateway = Gateway()
    gateway.context.update(
        {
            "node": {
                "status": "ok",
                "available": True,
                "result": {"role": "control"},
                "error": None,
            },
            "wire": {
                "status": "error",
                "available": True,
                "result": None,
                "error": {"type": "ConnectionError", "message": "offline"},
            },
            "errors": {
                "status": "ok",
                "available": True,
                "result": [{"message": "CRITICAL failure"}],
                "error": None,
            },
            "deploy": {
                "status": "unavailable",
                "available": False,
                "result": None,
                "error": {"type": "LookupError", "message": "missing"},
            },
        }
    )

    result = gateway(
        "observation collect node wire errors deploy --problems true"
    )

    assert set(result) == {
        "wire",
        "errors",
        "health",
        "changed_at",
        "cursor",
    }
    assert result["health"]["status"] == "degraded"
    assert result["health"]["sections"] == {
        "wire": "error",
        "errors": "ok",
    }


def test_observation_collect_problems_omits_empty_error_log_section():
    gateway = Gateway()
    gateway.context["errors"] = {
        "status": "ok",
        "available": True,
        "result": [],
        "error": None,
    }

    result = gateway("observation collect errors --problems true")

    assert set(result) == {"health", "changed_at", "cursor"}
    assert result["health"]["status"] == "ok"
    assert result["health"]["sections"] == {}


def test_observation_validate_requires_cursor_for_changed():
    gateway = Gateway()

    with pytest.raises(ValueError, match="requires --cursor"):
        gateway("observation validate --changed true")


def test_observation_cursor_detects_changed_section():
    gateway = Gateway()
    gateway.context["node"] = {
        "status": "ok",
        "available": True,
        "result": {"role": "control"},
        "error": None,
    }

    first = gateway("observation collect node")
    gateway.context["node"] = {
        "status": "ok",
        "available": True,
        "result": {"role": "watchtower"},
        "error": None,
    }
    second = gateway(
        f"observation collect node --changed true --cursor {first['cursor']}"
    )

    assert second["node"]["result"] == {"role": "watchtower"}
    assert second["health"]["sections"] == {"node": "ok"}
    assert second["changed_at"] is not None
    assert second["cursor"] != first["cursor"]


def test_observation_cursor_unchanged_result_is_empty_surface():
    gateway = Gateway()
    gateway.context["node"] = {
        "status": "ok",
        "available": True,
        "result": {"role": "control"},
        "error": None,
    }

    first = gateway("observation collect node")
    second = gateway(
        f"observation collect node --changed true --cursor {first['cursor']}"
    )

    assert set(second) == {"health", "changed_at", "cursor"}
    assert second["health"]["sections"] == {}
    assert second["changed_at"] is None


def test_observe_section_publishes_envelope_to_semantic_context():
    gateway = Gateway()
    gateway.wrap("probe", lambda *, mutate=False: {"ready": True})

    result = gateway("observe --section node -- probe")

    assert result["node"]["status"] == "ok"
    assert gateway.context["node"] == result["node"]


def test_observe_service_statuses_uses_canonical_authorized_operation():
    gateway = Gateway()

    with gateway.authorized(operations={"observe", "service.statuses"}):
        result = gateway("observe --section services -- service statuses")

    assert result["services"]["status"] == "ok"


def test_latest_explicit_wrap_replaces_same_canonical_operation():
    gateway = Gateway()
    calls = []
    gateway.wrap(
        "wire.check",
        lambda *, mutate=False: calls.append("replacement") or {"ready": False},
        op="check",
        sub="wire",
    )

    result = gateway("wire check")

    assert result == {"ready": False}
    assert calls == ["replacement"]
