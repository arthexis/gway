"""Shared fixtures for Sous Chef tests."""

import pytest

from gway.souschef import Job


@pytest.fixture
def job_factory(tmp_path):
    """Build Sous Chef jobs with concise project/name overrides."""

    def make(name, *, project="demo", root=None, timeout=900, **kwargs):
        base = tmp_path if root is None else root
        return Job(
            project=project,
            name=name,
            root=base,
            recipe=base / f"{name}.rx",
            timeout=timeout,
            **kwargs,
        )

    return make


@pytest.fixture
def recipe_factory():
    """Write one recipe and sibling Python companion."""

    def write(root, name, body, recipe_line):
        recipe = root / f"{name}.rx"
        companion = root / f"{name}.py"
        companion.write_text(body, encoding="utf-8")
        recipe.write_text(recipe_line + "\n", encoding="utf-8")
        return recipe

    return write


@pytest.fixture
def souschef_project():
    """Create the minimal local project used by command-surface tests."""

    def write(root):
        (root / "pyproject.toml").write_text(
            "[project]\n"
            "name = 'demo'\n"
            "\n"
            "[tool.gway.sous-chef.cleanup]\n"
            "recipe = 'cleanup.rx'\n"
            "every = '1h'\n"
            "timeout = '5m'\n",
            encoding="utf-8",
        )
        (root / "cleanup.py").write_text(
            "def mark():\n    return 'clean'\n",
            encoding="utf-8",
        )
        (root / "cleanup.rx").write_text(
            "cleanup mark\n",
            encoding="utf-8",
        )
        return root

    return write
