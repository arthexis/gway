from pathlib import Path

import pytest

from gway.install import Installation, InstallRequest, UninstallRequest


def test_installation_normalizes_path_and_preserves_source_identity(tmp_path):
    record = Installation(
        name="wire",
        source="https://github.com/arthexis/gway-wire",
        requested_ref="main",
        resolved_revision="abc123",
        fingerprint="sha256:deadbeef",
        install_path=tmp_path / "wire",
    )

    assert record.install_path == Path(tmp_path / "wire")
    assert record.scope == "user"
    assert record.requested_ref == "main"
    assert record.resolved_revision == "abc123"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"name": "", "source": "source"},
        {"name": "wire", "source": ""},
        {"name": "wire", "source": "source", "scope": "invalid"},
    ],
)
def test_installation_rejects_invalid_identity(kwargs, tmp_path):
    with pytest.raises(ValueError):
        Installation(install_path=tmp_path / "wire", **kwargs)


def test_install_request_defaults_to_convergent_upgrade():
    request = InstallRequest("arthexis/gway")

    assert request.upgrade is True
    assert request.force is False
    assert request.stash is False
    assert request.scope == "user"


def test_force_and_stash_are_mutually_exclusive():
    with pytest.raises(ValueError, match="mutually exclusive"):
        InstallRequest("arthexis/gway", force=True, stash=True)


def test_uninstall_request_is_scope_aware():
    request = UninstallRequest("gway", system=True)

    assert request.project == "gway"
    assert request.scope == "system"
