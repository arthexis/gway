from gway.security.scopes import ScopeRegistry
from gway.security.validation import validate_scope


def _operation(gateway, name, *, mutates):
    wrapped = gateway.wrap(name, lambda: None)
    wrapped.mutates = mutates
    wrapped.__gway_mutates__ = mutates
    return wrapped


def test_scope_name_does_not_imply_read_only_authority(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    _operation(gateway, "demo.create", mutates=True)

    scope = gateway("security scope set demo-read demo.create")
    result = gateway("security scope validate demo-read")

    assert scope.operations == frozenset({"demo.create"})
    assert result.valid is True
    assert result.mutating == ("demo.create",)
    assert result.registered == ("demo.create",)
    assert result.missing == ()
    assert result.unknown == ()
    assert result.mutation_capable is True


def test_scope_is_read_only_only_when_every_member_is_proven_non_mutating(
    gateway,
    tmp_path,
):
    gateway.security_path = tmp_path / "security.sqlite"
    _operation(gateway, "demo.read", mutates=False)
    _operation(gateway, "demo.list", mutates=False)

    gateway("security scope set observer demo.read demo.list")
    result = gateway("security scope validate observer")

    assert result.valid is True
    assert result.registered == ("demo.list", "demo.read")
    assert result.missing == ()
    assert result.mutating == ()
    assert result.unknown == ()
    assert result.mutation_capable is False


def test_unknown_member_is_conservatively_mutation_capable(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"

    scope = gateway("security scope set future-bundle demo.future")
    result = gateway("security scope validate future-bundle")

    assert scope.operations == frozenset({"demo.future"})
    assert result.valid is True
    assert result.registered == ()
    assert result.missing == ("demo.future",)
    assert result.mutating == ()
    assert result.unknown == ("demo.future",)
    assert result.mutation_capable is True


def test_mixed_bundle_reports_live_and_missing_members_separately(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    _operation(gateway, "demo.read", mutates=False)
    _operation(gateway, "demo.write", mutates=True)

    gateway("security scope set operator demo.read demo.write demo.future")
    result = gateway("security scope validate operator")

    assert result.valid is True
    assert result.registered == ("demo.read", "demo.write")
    assert result.missing == ("demo.future",)
    assert result.mutating == ("demo.write",)
    assert result.unknown == ("demo.future",)
    assert result.mutation_capable is True


def test_scope_inspect_reports_exact_grants_owner_and_stale_bindings(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    _operation(gateway, "demo.read", mutates=False)
    registry = ScopeRegistry(gateway.security_path)
    registry.replace_owned(
        "observer",
        owner="demo-extension",
        operations={"demo.read", "demo.retired"},
        environment={"DEMO_ENV"},
    )

    result = gateway("security scope inspect observer")

    assert result == {
        "name": "observer",
        "owner": "demo-extension",
        "operations": ["demo.read", "demo.retired"],
        "environment": ["DEMO_ENV"],
        "registered": ["demo.read"],
        "missing": ["demo.retired"],
        "mutating": [],
        "unknown": ["demo.retired"],
        "mutation_capable": True,
    }


def test_registry_definitions_reject_retired_semantic_metadata(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")

    try:
        registry.replace_many(
            {
                "legacy": {
                    "operations": ["demo.read"],
                    "semantic_terms": ["demo", "read"],
                }
            }
        )
    except ValueError as exc:
        assert "semantic_terms" in str(exc)
    else:
        raise AssertionError("retired semantic metadata unexpectedly accepted")


def test_validation_does_not_mutate_persisted_scope(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    _operation(gateway, "demo.write", mutates=True)
    registry = ScopeRegistry(gateway.security_path)
    registry.replace("bundle", operations={"demo.write"})

    before = registry.require("bundle")
    result = validate_scope(gateway, before)
    after = registry.require("bundle")

    assert result.mutation_capable is True
    assert after == before
