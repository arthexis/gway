from pathlib import Path
from types import SimpleNamespace

import pytest

from gway import uv


def test_managed_uv_path_lives_under_gway_data(monkeypatch, tmp_path):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))

    path = uv.managed_uv_path()

    assert path.parent == (tmp_path / "data" / "tools" / "uv").resolve()
    assert path.name in {"uv", "uv.exe"}


def test_find_uv_prefers_gway_managed_binary(monkeypatch, tmp_path):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    managed = uv.managed_uv_path()
    managed.parent.mkdir(parents=True)
    managed.write_text("", encoding="utf-8")
    monkeypatch.setattr(uv.shutil, "which", lambda name: "/usr/bin/uv")

    assert uv.find_uv() == managed.resolve()


def test_find_uv_falls_back_to_path(monkeypatch, tmp_path):
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))
    external = tmp_path / "bin" / "uv"
    external.parent.mkdir(parents=True)
    external.write_text("", encoding="utf-8")
    monkeypatch.setattr(uv.shutil, "which", lambda name: str(external))

    assert uv.find_uv() == external.resolve()


def test_ensure_uv_bootstraps_only_when_missing(monkeypatch, tmp_path):
    managed = tmp_path / "managed-uv"
    calls = []

    monkeypatch.setattr(uv, "find_uv", lambda **kwargs: None)

    def bootstrap(**kwargs):
        calls.append(kwargs)
        return managed

    monkeypatch.setattr(uv, "bootstrap_uv", bootstrap)

    assert uv.ensure_uv(system=True) == managed
    assert calls == [{"system": True}]


def test_ensure_uv_uses_existing_without_bootstrap(monkeypatch, tmp_path):
    existing = tmp_path / "uv"
    monkeypatch.setattr(uv, "find_uv", lambda **kwargs: existing)

    def forbidden(**kwargs):
        raise AssertionError("bootstrap should not run")

    monkeypatch.setattr(uv, "bootstrap_uv", forbidden)

    assert uv.ensure_uv() == existing


@pytest.mark.skipif(uv.os.name == "nt", reason="POSIX installer path")
def test_posix_bootstrap_uses_unmanaged_install_without_path_mutation(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(uv, "_download_text", lambda url: "# installer")
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        target = Path(kwargs["env"]["UV_UNMANAGED_INSTALL"])
        target.mkdir(parents=True, exist_ok=True)
        (target / "uv").write_text("", encoding="utf-8")
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(uv.subprocess, "run", run)
    monkeypatch.setenv("GWAY_DATA_DIR", str(tmp_path / "data"))

    result = uv.bootstrap_uv()

    assert result == uv.managed_uv_path().resolve()
    assert len(calls) == 1
    argv, kwargs = calls[0]
    assert argv == ["sh"]
    assert kwargs["input"] == "# installer"
    assert kwargs["text"] is True
    assert kwargs["check"] is True
    assert kwargs["env"]["UV_UNMANAGED_INSTALL"] == str(uv.managed_uv_root())
    assert kwargs["env"]["UV_NO_MODIFY_PATH"] == "1"


def test_require_bootstraps_uv_once_per_recipe_frame(gateway, monkeypatch, tmp_path):
    recipe = tmp_path / "demo.rx"
    recipe.write_text(
        "require fastmcp\n"
        "require cryptography\n"
        "uv probe\n",
        encoding="utf-8",
    )
    calls = []
    executable = tmp_path / "uv"

    def ensure_uv(**kwargs):
        calls.append(kwargs)
        return executable

    monkeypatch.setattr("gway.uv.ensure_uv", ensure_uv)

    def probe():
        return gateway._recipe_frames[-1].uv

    gateway.wrap("uv probe", probe)

    _, result = __import__("gway.recipes", fromlist=["execute_recipe"]).execute_recipe(
        gateway, recipe
    )

    assert result == executable
    assert calls == [{"system": False}]
