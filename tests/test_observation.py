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
