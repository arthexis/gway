from pathlib import Path

import pytest

from gway.souschef import DEFAULT_TIMEOUT, duration, jobs_from_data, load


def test_duration_parses_compact_units():
    assert duration("30s", "field") == 30.0
    assert duration("5m", "field") == 300.0
    assert duration("1h", "field") == 3600.0
    assert duration("2d", "field") == 172800.0


@pytest.mark.parametrize("value", [True, 0, -1, "", "15", "1w", "abc"])
def test_invalid_duration_is_rejected(value):
    with pytest.raises(ValueError, match="duration|greater than zero"):
        duration(value, "field")


def test_job_normalizes_paths_triggers_and_default_timeout(tmp_path):
    jobs = jobs_from_data(
        {
            "project": {"name": "demo"},
            "tool": {"gway": {"sous-chef": {
                "recover": {
                    "recipe": "recipes/recover.rx",
                    "every": "1h",
                    "watch": "config/settings.toml",
                    "down": "arthexis/web-local",
                }
            }}}
        },
        root=tmp_path,
    )

    assert len(jobs) == 1
    job = jobs[0]
    assert job.project == "demo"
    assert job.identity == ("demo", "recover")
    assert job.name == "recover"
    assert job.root == tmp_path.resolve()
    assert job.recipe == (tmp_path / "recipes/recover.rx").resolve()
    assert job.every == 3600.0
    assert job.watch == (tmp_path / "config/settings.toml").resolve()
    assert job.down == "arthexis/web-local"
    assert job.timeout == float(DEFAULT_TIMEOUT)
    assert job.triggers == ("every", "watch", "down")


def test_job_allows_explicit_timeout(tmp_path):
    job = jobs_from_data(
        {
            "project": {"name": "demo"},
            "tool": {"gway": {"sous-chef": {
                "build": {
                    "recipe": "recipes/build.rx",
                    "timeout": "5m",
                }
            }}}
        },
        root=tmp_path,
    )[0]

    assert job.timeout == 300.0
    assert job.triggers == ()


def test_down_target_remains_opaque_for_future_target_types(tmp_path):
    target = "https://example.com/health"
    job = jobs_from_data(
        {
            "project": {"name": "demo"},
            "tool": {"gway": {"sous-chef": {
                "recover": {
                    "recipe": "recover.rx",
                    "down": target,
                }
            }}}
        },
        root=tmp_path,
    )[0]

    assert job.down == target


def test_absolute_paths_are_preserved(tmp_path):
    recipe = (tmp_path / "recipes" / "job.rx").resolve()
    watch = (tmp_path / "watched.txt").resolve()

    job = jobs_from_data(
        {
            "project": {"name": "demo"},
            "tool": {"gway": {"sous-chef": {
                "job": {
                    "recipe": str(recipe),
                    "watch": str(watch),
                }
            }}}
        },
        root=tmp_path / "other",
    )[0]

    assert job.recipe == recipe
    assert job.watch == watch


@pytest.mark.parametrize(
    ("job", "message"),
    [
        ({}, "recipe"),
        ({"recipe": 42}, "recipe"),
        ({"recipe": "a.rx", "watch": 42}, "watch"),
        ({"recipe": "a.rx", "down": ""}, "down"),
        ({"recipe": "a.rx", "timeout": "forever"}, "timeout"),
        ({"recipe": "a.rx", "unknown": True}, "unknown fields"),
    ],
)
def test_invalid_job_declarations_are_rejected(tmp_path, job, message):
    with pytest.raises(ValueError, match=message):
        jobs_from_data(
            {
                "project": {"name": "demo"},
                "tool": {"gway": {"sous-chef": {"demo": job},
            },
            root=tmp_path,
        )


def test_sous_chef_section_must_be_a_table(tmp_path):
    with pytest.raises(ValueError, match="must be a table"):
        jobs_from_data(
            {
                "project": {"name": "demo"},
                "tool": {"gway": {"sous-chef": []}},
            },
            root=tmp_path,
        )



def test_hyphenated_sous_chef_toml_section_loads(tmp_path):
    manifest = tmp_path / "pyproject.toml"
    manifest.write_text(
        "[project]\n"
        "name = 'demo'\n"
        "\n"
        "[tool.gway.sous-chef.cleanup]\n"
        "recipe = 'recipes/cleanup.rx'\n"
        "every = '1h'\n"
        "timeout = '10m'\n",
        encoding="utf-8",
    )

    jobs = load(manifest)

    assert len(jobs) == 1
    assert jobs[0].name == "cleanup"
    assert jobs[0].recipe == (tmp_path / "recipes/cleanup.rx").resolve()
    assert jobs[0].every == 3600.0
    assert jobs[0].timeout == 600.0
