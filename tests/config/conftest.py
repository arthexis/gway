import pytest

import gway.ingestion.django as django_ingestor


@pytest.fixture
def django_ingest_spy(monkeypatch):
    """Capture declarative Django ingestion calls."""
    seen = {}

    def fake(runtime, source, **kwargs):
        seen["source"] = source
        seen["kwargs"] = kwargs
        return "mounted"

    monkeypatch.setattr(django_ingestor, "ingest_project", fake)
    return seen
