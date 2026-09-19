from pathlib import Path

import pytest

from gway import Gateway
import gway.config as config
import gway.ingestion.django as django_ingestor


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
    seen = {}

    def fake(runtime, source, **kwargs):
        seen["source"] = source
        seen["kwargs"] = kwargs
        return "mounted"

    monkeypatch.setattr(django_ingestor, "ingest_project", fake)
    monkeypatch.chdir(elsewhere)

    assert config.load_ingestions(gateway, manifest) == ["mounted"]
    assert seen == {
        "source": manage.resolve(),
        "kwargs": {"name": "arthexis"},
    }


def test_gateway_bootstraps_nearest_gway_toml_before_commands(
    tmp_path,
    monkeypatch,
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
    seen = {}

    def fake(runtime, source, **kwargs):
        seen["runtime"] = runtime
        seen["source"] = source
        seen["kwargs"] = kwargs
        return "mounted"

    monkeypatch.setattr(django_ingestor, "ingest_project", fake)
    monkeypatch.chdir(nested)

    runtime = Gateway()

    assert seen["runtime"] is runtime
    assert seen["source"] == manage.resolve()
    assert seen["kwargs"] == {"name": "arthexis"}
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
