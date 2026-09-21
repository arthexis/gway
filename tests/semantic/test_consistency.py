import pytest

from gway.dispatch import CheckError
from gway.semantic import AmbiguousKeyError


def _producer(gateway, result):
    def operation():
        return result

    gateway.probe_semantic = gateway.wrap("probe_semantic", operation)


@pytest.mark.parametrize(
    "requested",
    [
        "status_code",
        "status-code",
        "status code",
        "StatusCode",
        "STATUS_CODE",
    ],
)
def test_semantic_key_normalization_is_shared_across_surfaces(gateway, requested):
    result = {"Status Code": 200}
    _producer(gateway, result)

    assert (
        gateway(f"probe_semantic - check --{requested.replace(' ', '-')} 200") is result
    )
    assert gateway.resolve(f"[{requested}]") == 200

    def consume_status(status_code):
        return status_code

    gateway.consume_status = gateway.wrap("consume_status", consume_status)
    assert gateway("consume_status") == 200


def test_nested_sigil_uses_same_semantic_key_normalization(gateway):
    gateway.context["service"] = {
        "Health Status": {
            "Status-Code": 200,
        }
    }

    assert gateway.resolve("[service health_status status_code]") == 200
    assert gateway.resolve("[service HealthStatus STATUS-CODE]") == 200


def test_ambiguity_is_rejected_consistently_by_sigil_completion_and_check(gateway):
    ambiguous = {
        "status-code": 200,
        "status_code": 500,
    }
    gateway.context.update(ambiguous)

    with pytest.raises(AmbiguousKeyError):
        gateway.resolve("[status code]")

    def consume_status(status_code):
        return status_code

    wrapped = gateway.wrap("consume_status", consume_status)
    with pytest.raises(AmbiguousKeyError):
        wrapped()

    _producer(gateway, ambiguous)
    with pytest.raises(CheckError, match="ambiguous"):
        gateway("probe_semantic - check --status-code 200")


def test_nested_mapping_ambiguity_is_not_silently_resolved(gateway):
    gateway.context["service"] = {
        "health-status": {"code": 200},
        "health_status": {"code": 500},
    }

    with pytest.raises(AmbiguousKeyError):
        gateway.resolve("[service health_status code]")

    with pytest.raises(AmbiguousKeyError):
        gateway["service health_status code"]

    with pytest.raises(AmbiguousKeyError):
        gateway.get("service health_status code")
