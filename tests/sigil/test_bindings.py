from pathlib import Path

from gway.bindings import env, file, secret


def test_multiple_environment_aliases_use_declared_order(gateway, monkeypatch):
    gateway.bind("service.vendor.token", env("VENDOR_TOKEN"), env("VENDOR_TOKEN_OLD"))
    monkeypatch.setenv("VENDOR_TOKEN", "primary")
    monkeypatch.setenv("VENDOR_TOKEN_OLD", "legacy")

    with gateway.topics("service", "vendor"):
        assert gateway.resolve("[token]") == "primary"


def test_environment_binding_prefers_optional_gway_prefix(gateway, monkeypatch):
    gateway.bind("service.vendor.token", env("VENDOR_TOKEN"))
    monkeypatch.setenv("VENDOR_TOKEN", "shared")
    monkeypatch.setenv("GWAY_VENDOR_TOKEN", "gway-specific")

    with gateway.topics("service", "vendor"):
        assert gateway.resolve("[token]") == "gway-specific"


def test_explicit_gway_environment_binding_is_not_double_prefixed(
    gateway, monkeypatch
):
    gateway.bind("service.vendor.token", env("GWAY_VENDOR_TOKEN"))
    monkeypatch.setenv("GWAY_VENDOR_TOKEN", "explicit")
    monkeypatch.setenv("GWAY_GWAY_VENDOR_TOKEN", "wrong")

    with gateway.topics("service", "vendor"):
        assert gateway.resolve("[token]") == "explicit"


def test_multiple_file_bindings_fall_through_in_declared_order(gateway, tmp_path):
    missing = tmp_path / "missing"
    second = tmp_path / "second"
    second.write_text("file-secret\n", encoding="utf-8")
    gateway.bind("service.vendor.token", file(missing), file(second))

    with gateway.topics("service", "vendor"):
        assert gateway.resolve("[token]") == "file-secret"


def test_environment_and_file_bindings_share_one_declared_order(
    gateway, monkeypatch, tmp_path
):
    secret = tmp_path / "token"
    secret.write_text("file-value\n", encoding="utf-8")
    monkeypatch.setenv("VENDOR_TOKEN", "environment-value")
    gateway.bind("service.vendor.token", file(secret), env("VENDOR_TOKEN"))

    with gateway.topics("service", "vendor"):
        assert gateway.resolve("[token]") == "file-value"


def test_unreadable_optional_file_binding_falls_through(
    gateway, monkeypatch, tmp_path
):
    blocked = tmp_path / "blocked"
    fallback = tmp_path / "fallback"
    blocked.write_text("blocked", encoding="utf-8")
    fallback.write_text("fallback\n", encoding="utf-8")
    original = Path.read_text

    def read_text(path, *args, **kwargs):
        if path == blocked:
            raise PermissionError("blocked")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    gateway.bind("service.vendor.token", file(blocked), file(fallback))

    with gateway.topics("service", "vendor"):
        assert gateway.resolve("[token]") == "fallback"


def test_semantic_specificity_beats_physical_gway_prefix(
    gateway, monkeypatch
):
    gateway.bind("dns.godaddy.api_key", env("GODADDY_API_KEY"))
    gateway.bind("api_key", env("API_KEY"))
    monkeypatch.setenv("GODADDY_API_KEY", "specific")
    monkeypatch.setenv("GWAY_API_KEY", "generic-gway")

    with gateway.topics("dns", "godaddy"):
        assert gateway.resolve("[api_key]") == "specific"


def test_specific_file_binding_beats_broader_environment_binding(
    gateway, monkeypatch, tmp_path
):
    secret = tmp_path / "specific"
    secret.write_text("specific-file\n", encoding="utf-8")
    gateway.bind("dns.godaddy.api_key", file(secret))
    gateway.bind("api_key", env("API_KEY"))
    monkeypatch.setenv("GWAY_API_KEY", "generic-environment")

    with gateway.topics("dns", "godaddy"):
        assert gateway.resolve("[api_key]") == "specific-file"


def test_physical_binding_respects_order_insensitive_topics(gateway, monkeypatch):
    gateway.bind("dns.godaddy.api_key", env("GODADDY_API_KEY"))
    monkeypatch.setenv("GODADDY_API_KEY", "bound")

    with gateway.topics("godaddy", "dns"):
        assert gateway.resolve("[api_key]") == "bound"



def test_secret_binding_uses_configured_root_and_marks_resolution_sensitive(
    gateway, monkeypatch, tmp_path
):
    root = tmp_path / "secrets"
    target = root / "service" / "vendor" / "token"
    target.parent.mkdir(parents=True)
    target.write_text("sensitive-value\n", encoding="utf-8")
    monkeypatch.setenv("GWAY_SECRETS_DIR", str(root))
    gateway.bind("service.vendor.token", secret("service/vendor/token"))

    with gateway.topics("service", "vendor"):
        assert gateway.resolve("[token]") == "sensitive-value"

    resolution = gateway.bindings.resolution("service.vendor.token")
    assert resolution.sensitive is True
    assert resolution.source == "secret:service/vendor/token"


def test_sensitive_environment_binding_preserves_provenance(
    gateway, monkeypatch
):
    monkeypatch.setenv("VENDOR_TOKEN", "sensitive-value")
    gateway.bind(
        "service.vendor.token",
        env("VENDOR_TOKEN", sensitive=True),
    )

    with gateway.topics("service", "vendor"):
        assert gateway.resolve("[token]") == "sensitive-value"

    resolution = gateway.bindings.resolution("service.vendor.token")
    assert resolution.sensitive is True
    assert resolution.source == "env:VENDOR_TOKEN"
