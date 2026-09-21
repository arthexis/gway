from pathlib import Path


def repository_root():
    return Path(__file__).resolve().parents[2]


def test_sampler_has_one_canonical_repository_root():
    root = repository_root()
    sampler = root / "sampler"

    assert sampler.is_dir()
    assert any(sampler.rglob("*.rx"))
    assert sampler.parent == root
    assert [path for path in root.rglob("sampler") if path.is_dir()] == [sampler]


def test_sampler_is_not_implemented_as_a_bundled_recipe_tree():
    root = repository_root()

    assert not (root / "gway" / "bundled").exists()
    assert not (root / "gway" / "bundled.py").exists()


def test_sampler_contains_gway_and_arthexis_recipe_families():
    root = repository_root() / "sampler"

    assert (root / "web" / "expose" / "expose.rx").is_file()
    assert (root / "arthexis" / "setup.rx").is_file()
    assert (root / "arthexis" / "expose.rx").is_file()
