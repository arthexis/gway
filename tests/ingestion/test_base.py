import inspect

import pytest

from gway.ingestion import (
    IngestedOperation,
    canonical_name,
    normalize_path,
    register_operation,
    register_operations,
)


def test_normalize_path_accepts_dotted_and_iterable_paths():
    assert normalize_path("client.chargers.start") == ("client", "chargers", "start")
    assert normalize_path(("client", "chargers", "start")) == (
        "client",
        "chargers",
        "start",
    )
    assert canonical_name(("client", "chargers", "start")) == "client.chargers.start"


def test_empty_ingestion_path_is_rejected():
    with pytest.raises(ValueError, match="cannot be empty"):
        normalize_path(())


def test_ingested_operation_requires_callable():
    with pytest.raises(TypeError, match="not callable"):
        IngestedOperation(("client", "value"), 42)


def test_register_operation_wraps_and_registers_canonical_path(gateway):
    source = object()

    def start(service):
        return f"start:{service}"

    spec = IngestedOperation(
        ("systemctl", "start"),
        start,
        source=source,
        kind="python-test",
        metadata={"origin": "unit"},
    )

    wrapped = register_operation(gateway, spec)

    assert gateway.ops.resolve("systemctl.start") is wrapped
    assert wrapped.__gway_source__ is source
    assert wrapped.__gway_source_kind__ == "python-test"
    assert wrapped.__gway_path__ == ("systemctl", "start")
    assert wrapped.__gway_metadata__["origin"] == "unit"
    assert gateway("systemctl start arthexis") == "start:arthexis"


def test_register_operation_registers_aliases_without_changing_semantic_path(gateway):
    def status(service):
        return service

    spec = IngestedOperation(
        ("systemctl", "status"),
        status,
        aliases=("svc-status",),
    )
    wrapped = register_operation(gateway, spec)

    assert gateway.ops.resolve("svc-status") is wrapped
    assert wrapped.__gway_path__ == ("systemctl", "status")


def test_register_operations_preserves_input_order(gateway):
    def first():
        return 1

    def second():
        return 2

    wrapped = register_operations(
        gateway,
        [
            IngestedOperation(("demo", "first"), first),
            IngestedOperation(("demo", "second"), second),
        ],
    )

    assert [item() for item in wrapped] == [1, 2]


def test_ingested_operation_infers_reserved_mutation_contract():
    def reader(*, mutate=False):
        return mutate

    def writer():
        return None

    read_operation = IngestedOperation(("demo", "reader"), reader)
    write_operation = IngestedOperation(("demo", "writer"), writer)

    assert read_operation.mutates is False
    assert read_operation.supports_no_mutate is True
    assert write_operation.mutates is True
    assert write_operation.supports_no_mutate is False


def test_registered_operation_exposes_mutates_and_hides_reserved_parameter(gateway):
    def status(value="ok", *, mutate=False):
        return value, mutate

    wrapped = register_operation(
        gateway,
        IngestedOperation(("demo", "status"), status),
    )

    assert wrapped.mutates is False
    assert wrapped.__gway_mutates__ is False
    assert wrapped.__gway_supports_no_mutate__ is True
    assert "mutate" not in inspect.signature(wrapped).parameters
    assert gateway("demo status ready") == ("ready", False)


def test_mutate_parameter_must_have_boolean_default():
    def ambiguous(*, mutate=None):
        return mutate

    with pytest.raises(TypeError, match="must default to True or False"):
        IngestedOperation(("demo", "ambiguous"), ambiguous).mutates
