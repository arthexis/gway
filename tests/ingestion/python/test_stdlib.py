import hashlib
import json
import math
import operator

import pytest


@pytest.mark.parametrize(
    ("module", "operation"),
    [
        (operator, "operator.add"),
        (math, "math.sqrt"),
        (json, "json.loads"),
        (hashlib, "hashlib.sha256"),
    ],
)
def test_stdlib_modules_expose_direct_callables(gateway, module, operation):
    gateway.ingest(module)

    assert gateway.ops.resolve(operation) is not None


def test_operator_preserves_unannotated_cli_string_binding(gateway):
    gateway.ingest(operator)

    assert gateway("operator add 2 3") == "23"


def test_math_ingestion_does_not_descend_into_scalar_values(gateway):
    gateway.ingest(math)

    assert gateway("math sqrt", 9) == 3.0
    assert gateway.ops.resolve("math.pi.as_integer_ratio") is None


def test_json_class_members_remain_lazy(gateway):
    gateway.ingest(json)

    assert gateway.ops.resolve("json.JSONDecoder") is not None
    assert gateway.ops.resolve("json.JSONDecoder.decode") is None


def test_hashlib_container_members_are_not_eagerly_ingested(gateway):
    gateway.ingest(hashlib)

    assert gateway.ops.resolve("hashlib.algorithms_available.add") is None
