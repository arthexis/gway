import gway.ingestion.python as python_ingestor


def test_ingest_name_delegates_to_recursive_python_ingestion():
    names = set(python_ingestor.ingest_name.__code__.co_names)

    assert "import_module" in names
    assert "ingest_python" in names
    assert "register_operations" not in names
