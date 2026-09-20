import pytest

import gway.install.metadata as install_metadata


def test_install_metadata_falls_back_without_tomli(tmp_path, monkeypatch):
    metadata = tmp_path / "pyproject.toml"
    metadata.write_text(
        "[project]\n"
        "name = 'demo'\n"
        "\n"
        "[project.scripts]\n"
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

    monkeypatch.setattr(install_metadata.toml, "load", missing_tomli)

    data = install_metadata.load(metadata)

    assert data["project"]["name"] == "demo"
    assert data["project"]["scripts"] == {"demo": "demo:main"}


def test_install_metadata_does_not_hide_other_import_failures(tmp_path, monkeypatch):
    metadata = tmp_path / "pyproject.toml"
    metadata.write_text("[project]\nname = 'demo'\n", encoding="utf-8")

    def missing_other(path):
        error = ModuleNotFoundError("No module named 'other'")
        error.name = "other"
        raise error

    monkeypatch.setattr(install_metadata.toml, "load", missing_other)

    with pytest.raises(ModuleNotFoundError) as error:
        install_metadata.load(metadata)

    assert error.value.name == "other"
