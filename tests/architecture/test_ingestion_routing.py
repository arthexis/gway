import inspect

import gway.ingestion.python as python_ingestor
import gway.ingestion.proc as proc_ingestor
import gway.ingestion.router as router
from gway import Gateway


def test_python_ingestor_exposes_all_supported_source_forms():
    assert callable(python_ingestor.ingest_python)
    assert callable(python_ingestor.ingest_name)
    assert callable(python_ingestor.ingest_path)


def test_proc_ingestor_exposes_generic_and_path_entry_points():
    assert callable(proc_ingestor.ingest_proc)
    assert callable(proc_ingestor.ingest_path)


def test_gateway_owns_public_ingestion_entry_points():
    assert callable(Gateway.ingest)
    assert callable(Gateway.ingest_path)


def test_path_routing_is_separate_from_python_and_proc_implementation():
    names = set(router.ingest_path.__code__.co_names)
    assert "subprocess" not in names
    assert "import_module" not in names
