from pathlib import Path

import pytest

from gway.install.identity import (
    RuntimeIdentity,
    managed_gway_identity,
    running_gway_identity,
    runtime_identity,
)
from gway.install.model import Installation
from gway.install.state import InstallState
from gway.install.paths import install_paths


def _installation(tmp_path, **overrides):
    values = {
        "name": "gway",
        "source": "https://github.com/arthexis/gway.git",
        "requested_ref": "main",
        "resolved_revision": "abc123",
        "fingerprint": "fp-1",
        "install_path": tmp_path / "projects" / "gway",
        "scope": "user",
    }
    values.update(overrides)
    return Installation(**values)


def test_runtime_identity_normalizes_managed_installation(tmp_path):
    installation = _installation(tmp_path)

    identity = runtime_identity(installation)

    assert identity.source == installation.source
    assert identity.requested_ref == "main"
    assert identity.resolved_revision == "abc123"
    assert identity.fingerprint == "fp-1"
    assert identity.install_path == installation.install_path.resolve()
    assert identity.scope == "user"
    assert identity.comparable is True


def test_same_revision_and_fingerprint_is_same_runtime():
    first = RuntimeIdentity(resolved_revision="abc", fingerprint="fp")
    second = RuntimeIdentity(resolved_revision="abc", fingerprint="fp")

    assert first.same_runtime(second) is True


def test_different_revision_is_changed_even_when_fingerprint_matches():
    first = RuntimeIdentity(resolved_revision="abc", fingerprint="fp")
    second = RuntimeIdentity(resolved_revision="def", fingerprint="fp")

    assert first.same_runtime(second) is False


def test_same_revision_but_different_fingerprint_is_changed():
    first = RuntimeIdentity(resolved_revision="abc", fingerprint="fp-1")
    second = RuntimeIdentity(resolved_revision="abc", fingerprint="fp-2")

    assert first.same_runtime(second) is False


def test_single_shared_strong_identity_can_compare():
    assert RuntimeIdentity(resolved_revision="abc").same_runtime(
        RuntimeIdentity(resolved_revision="abc")
    )
    assert RuntimeIdentity(fingerprint="fp").same_runtime(
        RuntimeIdentity(fingerprint="fp")
    )


def test_identities_without_shared_strong_identity_are_not_comparable():
    with pytest.raises(ValueError, match="share no comparable"):
        RuntimeIdentity(resolved_revision="abc").same_runtime(
            RuntimeIdentity(fingerprint="fp")
        )

    with pytest.raises(ValueError, match="not comparable"):
        RuntimeIdentity(source="repo").same_runtime(RuntimeIdentity(source="repo"))


def test_managed_gway_identity_reads_authoritative_install_state(tmp_path):
    paths = install_paths(root=tmp_path / "data")
    state = InstallState(paths.state)
    installation = state.put(_installation(tmp_path))

    identity = managed_gway_identity(paths=paths, state=state)

    assert identity == runtime_identity(installation)


def test_managed_gway_identity_returns_none_when_unmanaged(tmp_path):
    paths = install_paths(root=tmp_path / "data")
    state = InstallState(paths.state)

    assert managed_gway_identity(paths=paths, state=state) is None


def test_diagnostic_prefers_code_identity_without_source_path():
    identity = RuntimeIdentity(
        source="/private/source/path",
        requested_ref="candidate",
        resolved_revision="abc123",
        fingerprint="fp-1",
        install_path=Path("/private/install/path"),
        scope="user",
    )

    diagnostic = identity.diagnostic()

    assert diagnostic == "revision=abc123 fingerprint=fp-1 ref=candidate scope=user"
    assert "/private/" not in diagnostic



def test_running_identity_requires_current_package_to_match_managed_install(tmp_path):
    paths = install_paths(root=tmp_path / "data")
    state = InstallState(paths.state)
    installation = state.put(_installation(tmp_path))

    assert running_gway_identity(
        package_root=installation.install_path,
        paths=paths,
        state=state,
    ) == runtime_identity(installation)

    assert running_gway_identity(
        package_root=tmp_path / "checkout",
        paths=paths,
        state=state,
    ) is None


def test_running_identity_is_none_without_managed_install(tmp_path):
    paths = install_paths(root=tmp_path / "data")
    state = InstallState(paths.state)

    assert running_gway_identity(
        package_root=tmp_path / "checkout",
        paths=paths,
        state=state,
    ) is None
