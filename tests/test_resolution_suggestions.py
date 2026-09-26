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


def test_resolution_error_ignores_command_arguments_when_scoring(gateway):
    gateway.wrap("install.package", lambda: "ok")

    with pytest.raises(OperationLookupError) as caught:
        gateway("instal package --upgrade")

    assert caught.value.suggestions[0] == "install package"


def test_resolution_error_filters_suggestions_by_active_authorization(gateway):
    gateway.wrap("delete.secret", lambda: "deleted")
    gateway.wrap("help", lambda: "help")

    with gateway.authorized(operations={"help"}):
        with pytest.raises(OperationLookupError) as caught:
            gateway("delet secret")

    assert "delete secret" not in caught.value.suggestions
