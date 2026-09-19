import json

from gway.install import Installation
from gway.install.stash import preserve


def test_preserve_stash_copies_managed_tree_and_metadata(tmp_path):
    managed = tmp_path / "projects" / "wire"
    managed.mkdir(parents=True)
    (managed / "custom.txt").write_text("custom\n", encoding="utf-8")
    stashes = tmp_path / "stashes"
    existing = Installation(
        name="wire",
        source="/source/wire",
        requested_ref="main",
        resolved_revision="abc123",
        fingerprint="sha256:recorded",
        install_path=managed,
    )

    stash = preserve(
        existing,
        managed,
        "sha256:actual",
        stashes,
    )

    assert stash.name == "wire"
    assert stash.path.parent == stashes / "wire"
    assert (stash.tree / "custom.txt").read_text(encoding="utf-8") == "custom\n"

    metadata = json.loads(
        (stash.path / "metadata.json").read_text(encoding="utf-8")
    )
    assert metadata["name"] == "wire"
    assert metadata["source"] == "/source/wire"
    assert metadata["requested_ref"] == "main"
    assert metadata["resolved_revision"] == "abc123"
    assert metadata["recorded_fingerprint"] == "sha256:recorded"
    assert metadata["actual_fingerprint"] == "sha256:actual"
    assert metadata["tree"] == "tree"


def test_preserve_stash_does_not_modify_managed_tree(tmp_path):
    managed = tmp_path / "projects" / "wire"
    managed.mkdir(parents=True)
    marker = managed / "custom.txt"
    marker.write_text("custom\n", encoding="utf-8")
    existing = Installation(
        name="wire",
        source="/source/wire",
        fingerprint="sha256:recorded",
        install_path=managed,
    )

    preserve(
        existing,
        managed,
        "sha256:actual",
        tmp_path / "stashes",
    )

    assert marker.read_text(encoding="utf-8") == "custom\n"
