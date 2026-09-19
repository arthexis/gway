import gway.ingestion.python as python_ingestor


def test_python_ingestion_separates_discovery_from_registration():
    assert callable(python_ingestor.discover_python)
    assert callable(python_ingestor.ingest_python)


def test_python_ingestor_uses_cycle_guard():
    names = set(python_ingestor.discover_python.__code__.co_names)
    assert "id" in names
