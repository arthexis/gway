import pytest

from gway.install import InstallRequest, UninstallRequest


def test_install_builtin_defaults_upgrade_on(gateway):
    request = gateway("install arthexis/gway")

    assert request == InstallRequest("arthexis/gway")
    assert request.upgrade is True


def test_install_builtin_supports_no_upgrade(gateway):
    request = gateway("install arthexis/gway --no-upgrade")

    assert request.source == "arthexis/gway"
    assert request.upgrade is False


def test_install_builtin_exposes_ref_and_scope(gateway):
    request = gateway(
        "install arthexis/gway --ref gateway-rebuild --system"
    )

    assert request == InstallRequest(
        "arthexis/gway",
        ref="gateway-rebuild",
        system=True,
    )


def test_install_builtin_rejects_force_with_stash(gateway):
    with pytest.raises(ValueError, match="mutually exclusive"):
        gateway("install arthexis/gway --force --stash")


def test_uninstall_builtin_returns_desired_absence_request(gateway):
    request = gateway("uninstall gway --system")

    assert request == UninstallRequest("gway", system=True)
