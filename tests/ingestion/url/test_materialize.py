import pytest

from gway.cache import Cache, digest
from gway.ingestion import url as url_ingestor


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("https://example.test/tool.py", True),
        ("http://example.test/tool.py", True),
        ("ftp://example.test/tool.py", False),
        ("./https://example.test/tool.py", False),
        ("package.module", False),
    ],
)
def test_url_detection(source, expected):
    assert url_ingestor.is_url(source) is expected


def test_url_materialization_is_cached_by_url_and_content(
    gateway,
    tmp_path,
    monkeypatch,
):
    gateway.cache = Cache(tmp_path / "cache")
    calls = []

    def fake_request(_method, url, **_kwargs):
        calls.append(url)
        return type(
            "Response",
            (),
            {
                "status": 200,
                "content": b"def ping():\n    return 'pong'\n",
                "url": url,
            },
        )()

    monkeypatch.setattr(url_ingestor, "http_request", fake_request)

    first = url_ingestor.materialize(
        gateway,
        "https://example.test/tool.py#fragment",
    )
    second = url_ingestor.materialize(
        gateway,
        "https://example.test/tool.py#fragment",
    )

    assert calls == ["https://example.test/tool.py"]
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second.path == first.path
    assert first.content_hash == digest(first.path.read_bytes())
    assert first.path.is_relative_to(gateway.cache.root)


def test_url_refresh_preserves_content_addressed_versions(
    gateway,
    tmp_path,
    monkeypatch,
):
    gateway.cache = Cache(tmp_path / "cache")
    payloads = iter([b"one", b"two"])

    monkeypatch.setattr(
        url_ingestor,
        "http_request",
        lambda _method, url, **_kwargs: type(
            "Response",
            (),
            {"status": 200, "content": next(payloads), "url": url},
        )(),
    )

    first = url_ingestor.materialize(
        gateway,
        "https://example.test/tool.py",
    )
    second = url_ingestor.materialize(
        gateway,
        "https://example.test/tool.py",
        refresh=True,
    )

    assert first.content_hash != second.content_hash
    assert first.path != second.path
    assert first.path.read_bytes() == b"one"
    assert second.path.read_bytes() == b"two"


def test_untrusted_remote_source_is_materialized_but_not_executed(
    gateway,
    tmp_path,
    monkeypatch,
):
    gateway.cache = Cache(tmp_path / "cache")
    monkeypatch.setattr(
        url_ingestor,
        "http_request",
        lambda _method, url, **_kwargs: type(
            "Response",
            (),
            {"status": 200, "content": b"print('remote')\n", "url": url},
        )(),
    )

    with pytest.raises(PermissionError, match="trust=True") as error:
        url_ingestor.ingest_url(
            gateway,
            "https://example.test/tool.py",
        )

    assert str(gateway.cache.root) in str(error.value)


def test_trusted_remote_source_delegates_to_path_ingestion(
    gateway,
    tmp_path,
    monkeypatch,
):
    gateway.cache = Cache(tmp_path / "cache")
    monkeypatch.setattr(
        url_ingestor,
        "http_request",
        lambda _method, url, **_kwargs: type(
            "Response",
            (),
            {"status": 200, "content": b"print('remote')\n", "url": url},
        )(),
    )
    seen = {}

    def fake_ingest_path(runtime, path, **kwargs):
        seen["runtime"] = runtime
        seen["path"] = path
        seen["kwargs"] = kwargs
        return "ingested"

    monkeypatch.setattr("gway.ingestion.router.ingest_path", fake_ingest_path)

    result = url_ingestor.ingest_url(
        gateway,
        "https://example.test/tool.py",
        trust=True,
        name="remote",
    )

    assert result == "ingested"
    assert seen["runtime"] is gateway
    assert seen["path"].is_relative_to(gateway.cache.root)
    assert seen["kwargs"] == {"name": "remote"}
