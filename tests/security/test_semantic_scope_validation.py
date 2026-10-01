import pytest

from gway.security.scopes import ScopeRegistry
from gway.security.validation import validate_scope


def _operation(gateway, name, *, mutates):
    wrapped = gateway.wrap(name, lambda: None)
    wrapped.mutates = mutates
    wrapped.__gway_mutates__ = mutates
    return wrapped


def test_semantic_read_scope_accepts_known_non_mutating_operations(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    _operation(gateway, "demo.read", mutates=False)

    scope = gateway("security scope set demo-read demo.read --semantic demo,read")

    assert scope.semantic_terms == frozenset({"demo", "read"})
    assert gateway("security scope validate demo-read").valid is True


def test_semantic_read_scope_rejects_mutating_operations(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    _operation(gateway, "demo.create", mutates=True)

    with pytest.raises(ValueError, match="mutating: demo.create"):
        gateway("security scope set demo-read demo.create --semantic demo,read")

    assert ScopeRegistry(gateway.security_path).get("demo-read") is None


def test_semantic_read_scope_rejects_unknown_operations(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"

    with pytest.raises(ValueError, match="unclassified or unavailable: demo.missing"):
        gateway("security scope set demo-read demo.missing --semantic demo,read")


def test_semantic_write_scope_may_contain_read_and_write_operations(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    _operation(gateway, "demo.read", mutates=False)
    _operation(gateway, "demo.create", mutates=True)

    scope = gateway(
        "security scope set demo-write demo.read demo.create --semantic demo,write"
    )

    assert scope.operations == frozenset({"demo.read", "demo.create"})
    assert gateway("security scope validate demo-write").valid is True


def test_legacy_exact_scope_remains_exempt_from_semantic_read_validation(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    _operation(gateway, "demo.create", mutates=True)

    scope = gateway("security scope set legacy demo.create")

    assert scope.semantic_terms == frozenset()
    assert gateway("security scope validate legacy").valid is True


def test_adding_mutator_to_existing_semantic_read_scope_fails_before_change(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    _operation(gateway, "demo.read", mutates=False)
    _operation(gateway, "demo.create", mutates=True)
    gateway("security scope set demo-read demo.read --semantic demo,read")

    with pytest.raises(ValueError, match="mutating: demo.create"):
        gateway("security scope add demo-read demo.create")

    assert ScopeRegistry(gateway.security_path).require("demo-read").operations == frozenset(
        {"demo.read"}
    )


def test_validation_reports_persisted_unsafe_read_scope_without_changing_it(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    _operation(gateway, "demo.create", mutates=True)
    registry = ScopeRegistry(gateway.security_path)
    registry.replace(
        "unsafe-read",
        operations={"demo.create"},
        semantic_terms={"demo", "read"},
    )

    result = validate_scope(gateway, registry.require("unsafe-read"))

    assert result.valid is False
    assert result.mutating == ("demo.create",)
    assert result.unknown == ()
