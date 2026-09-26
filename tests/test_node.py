import pytest

from gway import Gateway
from gway.authorization import AuthorizationError


def _runtime(tmp_path, monkeypatch, role):
    (tmp_path / "pyproject.toml").write_text(
        f"""
[project]
name = "demo"

[tool.gway.variables]
role = "{role}"
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    return Gateway()


def test_bare_node_reports_active_role_and_operations(tmp_path, monkeypatch):
    gateway = _runtime(tmp_path, monkeypatch, "watchtower")

    def diagnose():
        return {"ok": True}

    def audit():
        return {"secure": True}

    gateway.wrap("node.watchtower.diagnose", diagnose)
    gateway.wrap("node.watchtower.security.audit", audit)
    gateway.wrap("node.control.diagnose", diagnose)

    result = gateway("node")

    assert result == {
        "role": "watchtower",
        "family": "node/watchtower",
        "operations": ["diagnose", "security audit"],
    }


def test_node_dispatches_generic_verb_to_active_role(tmp_path, monkeypatch):
    gateway = _runtime(tmp_path, monkeypatch, "watchtower")

    def diagnose(target="local"):
        return {"role": "watchtower", "target": target}

    gateway.wrap("node.watchtower.diagnose", diagnose)

    assert gateway("node diagnose charger") == {
        "role": "watchtower",
        "target": "charger",
    }


def test_same_generic_node_verb_can_exist_for_multiple_roles(tmp_path, monkeypatch):
    gateway = _runtime(tmp_path, monkeypatch, "control")

    gateway.wrap(
        "node.watchtower.status",
        lambda: {"role": "watchtower"},
    )
    gateway.wrap(
        "node.control.status",
        lambda: {"role": "control"},
    )

    assert gateway("node status") == {"role": "control"}


def test_node_missing_role_operation_is_explicit(tmp_path, monkeypatch):
    gateway = _runtime(tmp_path, monkeypatch, "satellite")

    with pytest.raises(LookupError, match="does not expose node operation"):
        gateway("node diagnose")


def test_node_requires_active_role(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text(
        """
[project]
name = "demo"
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()

    with pytest.raises(LookupError, match="active semantic role"):
        gateway("node")


def test_bare_node_filters_operations_by_external_authority(tmp_path, monkeypatch):
    gateway = _runtime(tmp_path, monkeypatch, "watchtower")
    gateway.wrap("node.watchtower.status", lambda: {"ok": True})
    gateway.wrap("node.watchtower.audit", lambda: {"ok": True})

    with gateway.authorized(
        operations={"node", "node.watchtower.status"},
    ):
        result = gateway("node")

    assert result["operations"] == ["status"]


def test_node_dispatch_requires_concrete_role_operation_authority(
    tmp_path,
    monkeypatch,
):
    gateway = _runtime(tmp_path, monkeypatch, "watchtower")
    gateway.wrap("node.watchtower.status", lambda: {"ok": True})

    with gateway.authorized(operations={"node"}):
        with pytest.raises(
            AuthorizationError,
            match="node.watchtower.status",
        ):
            gateway("node status")


def test_node_dispatch_succeeds_with_both_authorities(tmp_path, monkeypatch):
    gateway = _runtime(tmp_path, monkeypatch, "watchtower")
    gateway.wrap("node.watchtower.status", lambda: {"ok": True})

    with gateway.authorized(
        operations={"node", "node.watchtower.status"},
    ):
        result = gateway("node status")

    assert result == {"ok": True}


def test_node_dispatches_longest_matching_multiword_verb(tmp_path, monkeypatch):
    gateway = _runtime(tmp_path, monkeypatch, "watchtower")

    def security_audit(target="local"):
        return {"audit": target}

    gateway.wrap("node.watchtower.security.audit", security_audit)

    assert gateway("node security audit charger") == {"audit": "charger"}


def test_node_prefers_longest_matching_role_operation(tmp_path, monkeypatch):
    gateway = _runtime(tmp_path, monkeypatch, "watchtower")

    def security(value):
        return {"security": value}

    def security_audit(target="local"):
        return {"audit": target}

    gateway.wrap("node.watchtower.security", security)
    gateway.wrap("node.watchtower.security.audit", security_audit)

    assert gateway("node security audit charger") == {"audit": "charger"}


def test_node_multiword_dispatch_authorizes_canonical_operation(
    tmp_path,
    monkeypatch,
):
    gateway = _runtime(tmp_path, monkeypatch, "watchtower")
    gateway.wrap(
        "node.watchtower.security.audit",
        lambda: {"secure": True},
    )

    with gateway.authorized(
        operations={"node", "node.watchtower.security.audit"},
    ):
        assert gateway("node security audit") == {"secure": True}

    with gateway.authorized(operations={"node"}):
        with pytest.raises(
            AuthorizationError,
            match="node.watchtower.security.audit",
        ):
            gateway("node security audit")


def test_active_role_node_operation_gets_role_oriented_alias(tmp_path, monkeypatch):
    gateway = _runtime(tmp_path, monkeypatch, "watchtower")
    gateway.wrap(
        "node.watchtower.status",
        lambda: {"role": "watchtower"},
    )

    assert gateway("watchtower status") == {"role": "watchtower"}


def test_role_oriented_alias_supports_multiword_operation(tmp_path, monkeypatch):
    gateway = _runtime(tmp_path, monkeypatch, "watchtower")
    gateway.wrap(
        "node.watchtower.security.audit",
        lambda target="local": {"audit": target},
    )

    assert gateway("watchtower security audit charger") == {
        "audit": "charger"
    }


def test_other_role_node_operation_does_not_get_local_role_alias(
    tmp_path,
    monkeypatch,
):
    gateway = _runtime(tmp_path, monkeypatch, "control")
    gateway.wrap(
        "node.watchtower.status",
        lambda: {"role": "watchtower"},
    )

    with pytest.raises(LookupError):
        gateway("watchtower status")


def test_role_oriented_alias_does_not_override_existing_operation(
    tmp_path,
    monkeypatch,
):
    gateway = _runtime(tmp_path, monkeypatch, "watchtower")
    gateway.wrap(
        "watchtower.status",
        lambda: {"source": "existing"},
    )
    gateway.wrap(
        "node.watchtower.status",
        lambda: {"source": "node"},
    )

    assert gateway("watchtower status") == {"source": "existing"}
    assert gateway("node status") == {"source": "node"}


def test_role_oriented_alias_authorizes_canonical_node_identity(
    tmp_path,
    monkeypatch,
):
    gateway = _runtime(tmp_path, monkeypatch, "watchtower")
    gateway.wrap(
        "node.watchtower.status",
        lambda: {"ok": True},
    )

    with gateway.authorized(
        operations={"node.watchtower.status"},
    ):
        assert gateway("watchtower status") == {"ok": True}

    with gateway.authorized(operations={"watchtower.status"}):
        with pytest.raises(
            AuthorizationError,
            match="node.watchtower.status",
        ):
            gateway("watchtower status")
