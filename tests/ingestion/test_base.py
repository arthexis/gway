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
