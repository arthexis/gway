import subprocess

import pytest

from gway.cache import Cache
from gway.install.git import (
    is_git_source,
    materialize,
    normalize_source,
)


def _git(*args, cwd=None):
    result = subprocess.run(
        ["git", *map(str, args)],
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return result.stdout.strip()


def _repository(tmp_path, name="wire"):
    source = tmp_path / "source"
    source.mkdir()
    _git("init", "-b", "main", cwd=source)
    _git("config", "user.name", "GWAY Tests", cwd=source)
    _git("config", "user.email", "gway@example.test", cwd=source)
    (source / "gway.toml").write_text(
        f"[project]\nname = {name!r}\n",
        encoding="utf-8",
    )
    (source / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    _git("add", ".", cwd=source)
    _git("commit", "-m", "initial", cwd=source)

    remote = tmp_path / "remote.git"
    _git("clone", "--bare", source, remote)
    _git("remote", "add", "origin", remote, cwd=source)
    return source, remote


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("arthexis/gway", "https://github.com/arthexis/gway.git"),
        (
            "https://github.com/arthexis/gway",
            "https://github.com/arthexis/gway.git",
        ),
        (
            "https://github.com/arthexis/gway.git",
            "https://github.com/arthexis/gway.git",
        ),
        (
            "git@github.com:arthexis/gway",
            "git@github.com:arthexis/gway.git",
        ),
    ],
)
def test_github_sources_are_normalized(source, expected):
    assert normalize_source(source) == expected
    assert is_git_source(source) is True


@pytest.mark.parametrize(
    "source",
    [
        "./local/project",
        "gway",
        "https://example.test/archive.tar.gz",
    ],
)
def test_non_git_sources_are_not_claimed(source):
    assert is_git_source(source) is False


def test_materialize_resolves_branch_to_immutable_commit(tmp_path):
    source, remote = _repository(tmp_path)
    cache = Cache(tmp_path / "cache")
    expected = _git("rev-parse", "HEAD", cwd=source)

    artifact = materialize(
        remote.as_uri(),
        ref="main",
        cache=cache,
    )

    assert artifact.requested_ref == "main"
    assert artifact.resolved_revision == expected
    assert artifact.path.is_dir()
    assert not (artifact.path / ".git").exists()
    assert (artifact.path / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert artifact.path.is_relative_to(cache.root)


def test_materialize_tracks_branch_movement(tmp_path):
    source, remote = _repository(tmp_path)
    cache = Cache(tmp_path / "cache")
    first = materialize(remote.as_uri(), ref="main", cache=cache)

    (source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git("add", "module.py", cwd=source)
    _git("commit", "-m", "second", cwd=source)
    _git("push", "origin", "main", cwd=source)

    second = materialize(remote.as_uri(), ref="main", cache=cache)

    assert second.resolved_revision != first.resolved_revision
    assert second.path != first.path
    assert first.path.is_dir()
    assert (first.path / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 1\n"
    assert (second.path / "module.py").read_text(
        encoding="utf-8"
    ) == "VALUE = 2\n"


def test_materialize_resolves_tag_and_commit_refs(tmp_path):
    source, remote = _repository(tmp_path)
    cache = Cache(tmp_path / "cache")
    revision = _git("rev-parse", "HEAD", cwd=source)
    _git("tag", "v1", cwd=source)
    _git("push", "origin", "v1", cwd=source)

    tagged = materialize(remote.as_uri(), ref="v1", cache=cache)
    committed = materialize(remote.as_uri(), ref=revision, cache=cache)

    assert tagged.resolved_revision == revision
    assert committed.resolved_revision == revision
    assert tagged.path == committed.path


def test_materialize_default_ref_uses_repository_head(tmp_path):
    source, remote = _repository(tmp_path)
    revision = _git("rev-parse", "HEAD", cwd=source)

    artifact = materialize(
        remote.as_uri(),
        cache=Cache(tmp_path / "cache"),
    )

    assert artifact.requested_ref is None
    assert artifact.resolved_revision == revision


def test_materialize_rejects_unknown_ref(tmp_path):
    _, remote = _repository(tmp_path)

    with pytest.raises(ValueError, match="Unable to resolve Git ref"):
        materialize(
            remote.as_uri(),
            ref="missing",
            cache=Cache(tmp_path / "cache"),
        )


def test_cached_snapshot_is_rebuilt_if_modified(tmp_path):
    _, remote = _repository(tmp_path)
    cache = Cache(tmp_path / "cache")
    first = materialize(remote.as_uri(), ref="main", cache=cache)
    target = first.path / "module.py"
    target.write_text("CORRUPT = True\n", encoding="utf-8")

    second = materialize(remote.as_uri(), ref="main", cache=cache)

    assert second.path == first.path
    assert target.read_text(encoding="utf-8") == "VALUE = 1\n"
