import pytest

import gway.install.manifest as install_manifest


def test_install_manifest_falls_back_without_tomli(tmp_path, monkeypatch):
    manifest = tmp_path / "gway.toml"
    manifest.write_text(
        "[project]\n"
        "name = 'demo'\n"
        "\n"
        "[install.scripts]\n"
        "demo = 'demo:main'\n"
        "\n"
        "[unrelated]\n"
        "value = 42\n",
        encoding="utf-8",
    )

    def missing_tomli(path):
        error = ModuleNotFoundError("No module named 'tomli'")
        error.name = "tomli"
        raise error

    monkeypatch.setattr(install_manifest.toml, "load", missing_tomli)

    data = install_manifest.load(manifest)

    assert data["project"]["name"] == "demo"
    assert data["install"]["scripts"] == {"demo": "demo:main"}


def test_install_manifest_does_not_hide_other_import_failures(tmp_path, monkeypatch):
    manifest = tmp_path / "gway.toml"
    manifest.write_text("[project]\nname = 'demo'\n", encoding="utf-8")

    def missing_other(path):
        error = ModuleNotFoundError("No module named 'other'")
        error.name = "other"
        raise error

    monkeypatch.setattr(install_manifest.toml, "load", missing_other)

    with pytest.raises(ModuleNotFoundError) as error:
        install_manifest.load(manifest)

    assert error.value.name == "other"
