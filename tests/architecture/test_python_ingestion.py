import gway.ingestion.python as python_ingestor


def test_python_ingestion_separates_discovery_from_registration():
    assert callable(python_ingestor.discover_python)
    assert callable(python_ingestor.ingest_python)


def test_discovery_is_one_level_and_identity_tracking_belongs_to_ingestion():
    discovery_names = set(python_ingestor.discover_python.__code__.co_names)
    ingestion_names = set(python_ingestor.ingest_python.__code__.co_names)

    assert "remember_object" not in discovery_names
    assert "remember_object" in ingestion_names
