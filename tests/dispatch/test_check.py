import pytest

from gway.dispatch import CheckError


def _producer(gateway, value, name="probe"):
    def operation():
        return value

    setattr(gateway, name, gateway.wrap(name, operation))


def test_check_is_compares_whole_pipeline_result(gateway):
    _producer(gateway, "ready")

    assert gateway("probe - check --is ready") == "ready"


def test_check_can_validate_previous_statement_result(gateway):
    _producer(gateway, "ready")

    assert gateway("probe ; check --is ready") == "ready"


@pytest.mark.parametrize(
    ("value", "flag"),
    [
        (True, "--true"),
        (False, "--false"),
    ],
)
def test_check_boolean_flags_require_exact_boolean_value(gateway, value, flag):
    _producer(gateway, value)

    assert gateway(f"probe - check {flag}") is value


def test_check_boolean_flag_rejects_opposite_value(gateway):
    _producer(gateway, False)

    with pytest.raises(CheckError, match="expected result to be true"):
        gateway("probe - check --true")


def test_check_boolean_flags_reject_non_boolean_truthy_result(gateway):
    _producer(gateway, 1)

    with pytest.raises(CheckError, match="requires a boolean result"):
        gateway("probe - check --true")


def test_check_named_flag_requires_mapping_key_presence(gateway):
    result = {"ready": False}
    _producer(gateway, result)

    assert gateway("probe - check --ready") is result


def test_check_named_flag_fails_when_mapping_key_is_missing(gateway):
    _producer(gateway, {"status": "healthy"})

    with pytest.raises(CheckError, match="'ready'.*present"):
        gateway("probe - check --ready")


def test_check_named_value_compares_mapping_value(gateway):
    result = {"status": "healthy", "code": 200}
    _producer(gateway, result)

    assert gateway("probe - check --status healthy --code 200") is result


def test_check_named_value_reports_wrong_mapping_value(gateway):
    _producer(gateway, {"status": "starting"})

    with pytest.raises(CheckError, match="'status'.*'healthy'.*'starting'"):
        gateway("probe - check --status healthy")


def test_check_named_value_reports_missing_mapping_key(gateway):
    _producer(gateway, {})

    with pytest.raises(CheckError, match="'status'.*present"):
        gateway("probe - check --status healthy")


def test_check_no_named_flag_requires_key_absence(gateway):
    result = {"status": "healthy"}
    _producer(gateway, result)

    assert gateway("probe - check --no-error") is result


def test_check_no_named_flag_fails_when_key_exists(gateway):
    _producer(gateway, {"error": None})

    with pytest.raises(CheckError, match="'error'.*absent"):
        gateway("probe - check --no-error")


def test_check_no_named_value_rejects_exact_pair(gateway):
    _producer(gateway, {"status": "failed"})

    with pytest.raises(CheckError, match="'status'.*not to equal 'failed'"):
        gateway("probe - check --no-status failed")


@pytest.mark.parametrize(
    "result",
    [
        {"status": "healthy"},
        {},
    ],
)
def test_check_no_named_value_allows_different_or_missing_value(gateway, result):
    _producer(gateway, result)

    assert gateway("probe - check --no-status failed") is result


def test_check_multiple_mapping_assertions_are_conjunctive(gateway):
    result = {
        "ready": True,
        "status": "healthy",
        "code": 200,
    }
    _producer(gateway, result)

    assert (
        gateway("probe - check --ready --status healthy --code 200 --no-error")
        is result
    )


def test_check_hyphenated_flag_maps_to_underscore_key(gateway):
    result = {"status_code": 200}
    _producer(gateway, result)

    assert gateway("probe - check --status-code 200") is result


def test_check_single_quoted_expected_value_stays_string(gateway):
    result = {"code": "200"}
    _producer(gateway, result)

    assert gateway("probe - check --code '200'") is result


def test_check_is_coerces_scalar_literals(gateway):
    _producer(gateway, 200)

    assert gateway("probe - check --is 200") == 200


def test_check_requires_at_least_one_assertion(gateway):
    _producer(gateway, True)

    with pytest.raises(TypeError, match="at least one assertion"):
        gateway("probe - check")


def test_named_check_requires_mapping_result(gateway):
    _producer(gateway, "ready")

    with pytest.raises(CheckError, match="requires a mapping result"):
        gateway("probe - check --status ready")


def test_check_returns_original_value_to_following_pipeline_stage(gateway):
    result = {"status": "healthy"}
    _producer(gateway, result)

    def consume(value):
        return value["status"]

    gateway.consume = gateway.wrap("consume", consume)

    assert gateway("probe - check --status healthy - consume") == "healthy"


@pytest.mark.parametrize(
    "key",
    [
        "status_code",
        "status-code",
        "status code",
        "StatusCode",
        "STATUS_CODE",
    ],
)
def test_check_named_keys_use_semantic_matching(gateway, key):
    result = {key: 200}
    _producer(gateway, result)

    assert gateway("probe - check --status-code 200") is result


def test_check_quoted_no_prefix_checks_literal_no_field(gateway):
    result = {"No Error": True}
    _producer(gateway, result)

    assert gateway("probe - check '--no-error' true") is result


def test_check_unquoted_no_prefix_still_inverts_semantic_field(gateway):
    _producer(gateway, {"No Error": True})

    with pytest.raises(CheckError, match="'no-error'.*absent"):
        gateway("probe - check --no-no-error")


def test_check_rejects_ambiguous_semantic_mapping_keys(gateway):
    _producer(
        gateway,
        {
            "status-code": 200,
            "status_code": 500,
        },
    )

    with pytest.raises(CheckError, match="ambiguous"):
        gateway("probe - check --status-code 200")


def test_checked_semantic_key_is_retrievable_after_publication(gateway):
    result = {"Status Code": 200}
    _producer(gateway, result)

    assert gateway("probe - check --status-code 200") is result
    assert gateway.resolve("[status_code]") == 200
    assert gateway.resolve("[STATUS-CODE]") == 200


def test_checked_semantic_key_can_bind_later_consumer_parameter(gateway):
    result = {"Status Code": 200}
    _producer(gateway, result)

    def consume_status(status_code):
        return status_code

    gateway.consume_status = gateway.wrap("consume_status", consume_status)

    assert gateway("probe ; check --status-code 200 ; consume_status") == 200
