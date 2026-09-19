from pathlib import Path

import pytest

from gway.install.source import fingerprint, local_source, named_source, project_name


def _project(tmp_path, name="demo"):
    root = tmp_path / name
    root.mkdir()
    (root / "gway.toml").write_text(
        f"[project]\nname = {name!r}\n",
        encoding="utf-8",
    )
    return root


def test_local_source_requires_existing_directory(tmp_path):
    missing = tmp_path / "missing"

    with pytest.raises(ValueError, match="does not exist"):
        local_source(missing)

    file = tmp_path / "project.txt"
    file.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a directory"):
        local_source(file)


def test_project_name_reads_required_manifest_identity(tmp_path):
    root = _project(tmp_path, "wire")

    assert project_name(root) == "wire"


def test_project_name_requires_gway_manifest(tmp_path):
    root = tmp_path / "plain"
    root.mkdir()

    with pytest.raises(ValueError, match="requires gway.toml"):
        project_name(root)


def test_project_name_requires_non_empty_name(tmp_path):
    root = tmp_path / "plain"
    root.mkdir()
    (root / "gway.toml").write_text("[project]\nname = ''\n", encoding="utf-8")

    with pytest.raises(ValueError, match="non-empty"):
        project_name(root)


def test_fingerprint_tracks_project_content_and_modes(tmp_path):
    root = _project(tmp_path)
    script = root / "run.sh"
    script.write_text("echo one\n", encoding="utf-8")
    script.chmod(0o644)

    first = fingerprint(root)
    script.write_text("echo two\n", encoding="utf-8")
    second = fingerprint(root)
    script.chmod(0o755)
    third = fingerprint(root)

    assert first != second
    assert second != third


def test_fingerprint_ignores_git_and_tool_cache_state(tmp_path):
    root = _project(tmp_path)
    (root / "module.py").write_text("VALUE = 1\n", encoding="utf-8")

    first = fingerprint(root)

    git = root / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    cache = root / "__pycache__"
    cache.mkdir()
    (cache / "module.pyc").write_bytes(b"compiled")

    assert fingerprint(root) == first


def test_fingerprint_tracks_symlink_target_without_following_it(tmp_path):
    root = _project(tmp_path)
    first = root / "one.txt"
    second = root / "two.txt"
    first.write_text("one", encoding="utf-8")
    second.write_text("two", encoding="utf-8")
    link = root / "current.txt"

    try:
        link.symlink_to(first.name)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are unavailable")

    initial = fingerprint(root)
    link.unlink()
    link.symlink_to(second.name)

    assert fingerprint(root) != initial



@pytest.mark.parametrize("name", ["../escape", "nested/name", "nested\\name", ".."])
def test_project_name_rejects_unsafe_path_components(tmp_path, name):
    root = tmp_path / "unsafe"
    root.mkdir()
    (root / "gway.toml").write_text(
        f"[project]\nname = {name!r}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=r"Invalid \[project\]\.name"):
        project_name(root)



def test_bare_gway_identity_resolves_repository_metadata():
    source = named_source("gway")

    assert source is not None
    assert source.endswith("/arthexis/gway.git")


def test_unknown_bare_project_identity_is_not_resolved():
    assert named_source("not-gway") is None
