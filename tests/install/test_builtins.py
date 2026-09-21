import pytest


@pytest.mark.parametrize(
    ("flags", "expected"),
    [
        ("", {"ref": None, "upgrade": True, "force": False, "stash": False, "system": False}),
        ("--ref main", {"ref": "main", "upgrade": True, "force": False, "stash": False, "system": False}),
        ("--no-upgrade", {"ref": None, "upgrade": False, "force": False, "stash": False, "system": False}),
        ("--force", {"ref": None, "upgrade": True, "force": True, "stash": False, "system": False}),
        ("--stash", {"ref": None, "upgrade": True, "force": False, "stash": True, "system": False}),
        ("--system", {"ref": None, "upgrade": True, "force": False, "stash": False, "system": True}),
    ],
)
def test_install_builtin_forwards_local_request(
    gateway,
    make_project,
    monkeypatch,
    flags,
    expected,
):
    source = make_project("wire")
    captured = {}
    sentinel = object()

    def install_local(request):
        captured["request"] = request
        return sentinel

    monkeypatch.setattr("gway.install.transaction.install_local", install_local)

    result = gateway(f"install {source} {flags}".strip())

    request = captured["request"]
    assert result is sentinel
    assert request.source == str(source)
    assert {
        "ref": request.ref,
        "upgrade": request.upgrade,
        "force": request.force,
        "stash": request.stash,
        "system": request.system,
    } == expected


def test_install_builtin_rejects_force_with_stash(gateway):
    with pytest.raises(ValueError, match="mutually exclusive"):
        gateway("install arthexis/gway --force --stash")


@pytest.mark.parametrize(
    ("flags", "system"),
    [
        ("", False),
        ("--system", True),
    ],
)
def test_uninstall_builtin_forwards_request(
    gateway,
    monkeypatch,
    flags,
    system,
):
    captured = {}
    sentinel = object()

    def uninstall_local(request):
        captured["request"] = request
        return sentinel

    monkeypatch.setattr("gway.install.transaction.uninstall_local", uninstall_local)

    result = gateway(f"uninstall wire {flags}".strip())

    request = captured["request"]
    assert result is sentinel
    assert request.project == "wire"
    assert request.system is system
