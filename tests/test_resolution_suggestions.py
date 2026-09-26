import pytest

from gway.dispatch import OperationLookupError


def test_resolution_error_suggests_close_registered_operation(gateway):
    gateway.wrap("status.service", lambda: "ok")

    with pytest.raises(OperationLookupError) as caught:
        gateway("statsu service")

    error = caught.value
    assert error.query == "statsu service"
    assert error.suggestions
    assert error.suggestions[0] == "status service"
    assert "Did you mean:" in str(error)
    assert "status service" in str(error)


def test_resolution_error_limits_ranked_suggestions(gateway):
    gateway.wrap("status.service", lambda: "status")
    gateway.wrap("start.service", lambda: "start")
    gateway.wrap("stop.service", lambda: "stop")
    gateway.wrap("restart.service", lambda: "restart")

    with pytest.raises(OperationLookupError) as caught:
        gateway("stat service")

    suggestions = caught.value.suggestions
    assert len(suggestions) <= 3
    assert "status service" in suggestions


def test_resolution_error_omits_low_confidence_suggestions(gateway):
    gateway.wrap("status.service", lambda: "ok")

    with pytest.raises(OperationLookupError) as caught:
        gateway("quantum banana")

    error = caught.value
    assert error.suggestions == ()
    assert str(error) == "Unable to resolve operation: quantum banana"


def test_resolution_error_remains_lookup_error_compatible(gateway):
    gateway.wrap("status.service", lambda: "ok")

    with pytest.raises(LookupError):
        gateway("statsu service")
