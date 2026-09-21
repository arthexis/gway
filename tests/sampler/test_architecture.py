from pathlib import Path


def repository_root():
    return Path(__file__).resolve().parents[2]


def test_sampler_remains_a_top_level_repository_concept():
    root = repository_root()
    sampler = root / "sampler"

    assert sampler.is_dir()
    assert any(sampler.rglob("*.rx"))
    assert sampler.parent == root
    assert root / "gway" not in sampler.parents


def test_sampler_is_not_folded_into_bundled_recipes():
    root = repository_root()
    bundled = root / "gway" / "bundled"

    assert not (bundled / "sampler").exists()
    assert not any(path.name == "sampler" for path in bundled.rglob("sampler"))
