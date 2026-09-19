import hashlib
import json
import math
import operator


def test_operator_ingests_direct_callables(gateway):
    gateway.ingest(operator)

    assert gateway.ops.resolve("operator.add") is not None
    assert gateway("operator add 2 3") == "23"


def test_math_ingestion_does_not_descend_into_values(gateway):
    gateway.ingest(math)

    assert gateway.ops.resolve("math.sqrt") is not None
    assert gateway("math sqrt", 9) == 3.0
    assert not any(name.startswith("math.pi.") for name in gateway.ops._registry.records)


def test_json_ingestion_stops_at_direct_members(gateway):
    gateway.ingest(json)

    assert gateway.ops.resolve("json.loads") is not None
    assert gateway.ops.resolve("json.JSONDecoder") is not None
    assert gateway.ops.resolve("json.JSONDecoder.decode") is None


def test_hashlib_does_not_expand_container_members(gateway):
    gateway.ingest(hashlib)

    assert gateway.ops.resolve("hashlib.sha256") is not None
    assert gateway.ops.resolve("hashlib.algorithms_available.add") is None
