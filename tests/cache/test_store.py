import pytest

from gway.cache import Cache, digest


def test_cache_is_lazy_until_namespace_is_used(tmp_path):
    root = tmp_path / "cache"
    cache = Cache(root)

    assert cache.root == root.resolve()
    assert not root.exists()

    namespace = cache.namespace("recipes")

    assert namespace == root.resolve() / "recipes"
    assert namespace.is_dir()


def test_cache_entries_are_namespaced_and_stably_hashed(tmp_path):
    cache = Cache(tmp_path / "cache")

    first = cache.entry("url", "https://example.test/tool.py")
    second = cache.entry("url", "https://example.test/tool.py")

    assert first == second
    assert first.parent.name == "url"
    assert first.name == digest("https://example.test/tool.py")


@pytest.mark.parametrize("name", ["", ".", "..", "../url", "url/name"])
def test_cache_namespace_rejects_unsafe_components(tmp_path, name):
    cache = Cache(tmp_path / "cache")

    with pytest.raises(ValueError, match="safe path component"):
        cache.namespace(name)


def test_cache_write_cannot_escape_root(tmp_path):
    cache = Cache(tmp_path / "cache")
    outside = tmp_path / "outside.bin"

    with pytest.raises(ValueError, match="inside the cache root"):
        cache.write(outside, b"data")


def test_cache_json_round_trip(tmp_path):
    cache = Cache(tmp_path / "cache")
    path = cache.entry("recipes", "deploy.rx") / "metadata.json"

    cache.write_json(path, {"hash": "abc", "version": 1})

    assert cache.read_json(path) == {"hash": "abc", "version": 1}
