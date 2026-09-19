from pathlib import Path

import pytest

from gway import Gateway
import gway.config as config


def test_find_manifest_uses_nearest_ancestor(tmp_path):
    project = tmp_path / "project"
    nested = project / "src" / "pkg"
    nested.mkdir(parents=True)
    manifest = project / "gway.toml"
    manifest.write_text("[project]\nname = 'demo'\n", encoding="utf-8")

    assert config.find_manifest(nested) == manifest


def test_find_manifest_returns_none_without_project_file(tmp_path):
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)

    assert config.find_manifest(nested) is None


def test_canonical_ingest_entry_inherits_declared_project_name_for_django():
    entries = config.ingestion_entries(
        {
            "project": {"name": "arthexis"},
            "ingest": [
                {
                    "source": "./manage.py",
                    "kind": "django",
                }
            ],
        }
    )

    assert entries == [
        {
            "source": "./manage.py",
            "kind": "django",
            "name": "arthexis",
        }
    ]


def test_explicit_ingest_name_overrides_project_name():
    entries = config.ingestion_entries(
        {
            "project": {"name": "workspace"},
            "ingest": [
                {
                    "source": "./manage.py",
                    "kind": "django",
                    "name": "backend",
                }
            ],
        }
    )

    assert entries[0]["name"] == "backend"


def test_unnamed_django_entry_stays_unnamed_without_project_name():
    entries = config.ingestion_entries(
        {
            "ingest": [
                {
                    "source": "./manage.py",
                    "kind": "django",
                }
            ],
        }
    )

    assert "name" not in entries[0]


def test_ingest_table_shorthand_uses_kind_keys_and_project_name():
    entries = config.ingestion_entries(
        {
            "project": {"name": "arthexis"},
            "ingest": {
                "django": "./manage.py",
                "python": "./tools.py",
            },
        }
    )

    assert entries == [
        {
            "kind": "django",
            "source": "./manage.py",
            "name": "arthexis",
        },
        {
            "kind": "python",
            "source": "./tools.py",
        },
    ]


def test_declarative_source_is_resolved_from_manifest_directory(
    gateway,
    tmp_path,
    monkeypatch,
    django_ingest_spy,
):
    project = tmp_path / "project"
    elsewhere = tmp_path / "elsewhere"
    project.mkdir()
    elsewhere.mkdir()
    manage = project / "manage.py"
    manage.write_text("# manage\n", encoding="utf-8")
    manifest = project / "gway.toml"
    manifest.write_text(
        "[project]\n"
        "name = 'arthexis'\n"
        "\n"
        "[[ingest]]\n"
        "source = './manage.py'\n"
        "kind = 'django'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(elsewhere)

    assert config.load_ingestions(gateway, manifest) == ["mounted"]
    assert django_ingest_spy == {
        "source": manage.resolve(),
        "kwargs": {"name": "arthexis"},
    }


def test_gateway_bootstraps_nearest_gway_toml_before_commands(
    tmp_path,
    monkeypatch,
    django_ingest_spy,
):
    project = tmp_path / "project"
    nested = project / "notebooks"
    nested.mkdir(parents=True)
    manage = project / "manage.py"
    manage.write_text("# manage\n", encoding="utf-8")
    (project / "gway.toml").write_text(
        "[project]\n"
        "name = 'arthexis'\n"
        "\n"
        "[[ingest]]\n"
        "source = './manage.py'\n"
        "kind = 'django'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(nested)

    runtime = Gateway()

    assert django_ingest_spy["source"] == manage.resolve()
    assert django_ingest_spy["kwargs"] == {"name": "arthexis"}
    assert runtime._manifest_path == (project / "gway.toml").resolve()


def test_gateway_with_manifest_but_no_ingest_table_starts_normally(
    tmp_path,
    monkeypatch,
):
    (tmp_path / "gway.toml").write_text(
        "[project]\nname = 'plain'\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    runtime = Gateway()

    assert runtime._manifest_path == (tmp_path / "gway.toml").resolve()
    assert runtime("env GWAY_CONFIG_TEST missing") == "missing"


def test_invalid_ingest_entry_fails_closed():
    with pytest.raises(ValueError, match="requires source"):
        config.ingestion_entries({"ingest": [{"kind": "django"}]})



def test_declarative_django_directory_infers_project_name_from_folder(
    gateway,
    tmp_path,
    django_ingest_spy,
):
    project = tmp_path / "backend"
    project.mkdir()
    (project / "manage.py").write_text("# manage\n", encoding="utf-8")
    manifest = tmp_path / "gway.toml"
    manifest.write_text(
        "[[ingest]]\n"
        "source = './backend'\n"
        "kind = 'django'\n",
        encoding="utf-8",
    )

    config.load_ingestions(gateway, manifest)

    assert django_ingest_spy == {
        "source": project.resolve(),
        "kwargs": {"name": "backend"},
    }


def test_declarative_manage_py_infers_project_name_from_parent_folder(
    gateway,
    tmp_path,
    django_ingest_spy,
):
    project = tmp_path / "billing"
    project.mkdir()
    manage = project / "manage.py"
    manage.write_text("# manage\n", encoding="utf-8")
    manifest = tmp_path / "gway.toml"
    manifest.write_text(
        "[[ingest]]\n"
        "source = './billing/manage.py'\n"
        "kind = 'django'\n",
        encoding="utf-8",
    )

    config.load_ingestions(gateway, manifest)

    assert django_ingest_spy == {
        "source": manage.resolve(),
        "kwargs": {"name": "billing"},
    }


def test_declarative_dot_django_source_uses_manifest_directory_name(
    gateway,
    tmp_path,
    django_ingest_spy,
):
    project = tmp_path / "arthexis"
    project.mkdir()
    (project / "manage.py").write_text("# manage\n", encoding="utf-8")
    manifest = project / "gway.toml"
    manifest.write_text(
        "[ingest]\n"
        "django = '.'\n",
        encoding="utf-8",
    )

    config.load_ingestions(gateway, manifest)

    assert django_ingest_spy == {
        "source": project.resolve(),
        "kwargs": {"name": "arthexis"},
    }


def test_declarative_settings_module_does_not_infer_name_from_text(
    gateway,
    tmp_path,
    django_ingest_spy,
):
    manifest = tmp_path / "gway.toml"
    manifest.write_text(
        "[[ingest]]\n"
        "source = 'config.settings'\n"
        "kind = 'django'\n",
        encoding="utf-8",
    )

    config.load_ingestions(gateway, manifest)

    assert django_ingest_spy == {
        "source": "config.settings",
        "kwargs": {},
    }


def test_explicit_declarative_name_beats_folder_inference(
    gateway,
    tmp_path,
    django_ingest_spy,
):
    project = tmp_path / "backend"
    project.mkdir()
    (project / "manage.py").write_text("# manage\n", encoding="utf-8")
    manifest = tmp_path / "gway.toml"
    manifest.write_text(
        "[[ingest]]\n"
        "source = './backend'\n"
        "kind = 'django'\n"
        "name = 'api'\n",
        encoding="utf-8",
    )
    config.load_ingestions(gateway, manifest)

    assert django_ingest_spy["kwargs"] == {"name": "api"}



def test_declarative_url_source_is_not_resolved_as_local_path(tmp_path):
    source = "https://example.test/tool.py"

    assert config._source_from_manifest(source, tmp_path) == source
