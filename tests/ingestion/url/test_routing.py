import gway.ingestion.url as url_ingestor
from gway.ingestion import ingest


def test_generic_ingest_routes_url_before_filesystem_detection(
    gateway,
    monkeypatch,
):
    seen = {}

    def fake(runtime, source, **kwargs):
        seen["source"] = source
        seen["kwargs"] = kwargs
        return "url"

    monkeypatch.setattr(url_ingestor, "ingest_url", fake)

    result = ingest(
        gateway,
        "https://example.test/tool.py",
        trust=True,
    )

    assert result == "url"
    assert seen == {
        "source": "https://example.test/tool.py",
        "kwargs": {"trust": True},
    }
