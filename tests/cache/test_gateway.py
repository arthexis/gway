from gway import Cache, Gateway


def test_gateway_accepts_explicit_cache_root(tmp_path):
    root = tmp_path / "cache"

    gateway = Gateway(cache=root)

    assert isinstance(gateway.cache, Cache)
    assert gateway.cache.root == root.resolve()
    assert not root.exists()


def test_gateway_reuses_explicit_cache_instance(tmp_path):
    cache = Cache(tmp_path / "cache")

    gateway = Gateway(cache=cache)

    assert gateway.cache is cache
