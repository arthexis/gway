import gway.ingestion.python as python_ingestor


def test_python_path_ingestion_delegates_after_loading():
    names = set(python_ingestor.ingest_path.__code__.co_names)

    assert "_load_path" in names
    assert "ingest_python" in names
    assert "register_operations" not in names


def test_python_path_loader_uses_importlib_spec_loading():
    names = set(python_ingestor._load_path.__code__.co_names)

    assert "spec_from_file_location" in names
    assert "module_from_spec" in names
