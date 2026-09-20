import gway.dispatch as dispatch
import gway.ingestion.base as base
import gway.ingestion.proc as proc_ingestor
import gway.ingestion.python as python_ingestor
import gway.ingestion.router as router
from gway import Gateway


def test_ingestion_base_exposes_source_agnostic_boundaries():
    assert callable(base.register_operation)
    assert callable(base.register_operations)
    assert callable(base.find_ingested)
    assert callable(base.expand_path)
    assert "subprocess" not in vars(base)
    assert "inspect" not in vars(base)


def test_python_ingestor_exposes_supported_source_forms():
    assert callable(python_ingestor.discover_python)
    assert callable(python_ingestor.ingest_python)
    assert callable(python_ingestor.ingest_name)
    assert callable(python_ingestor.ingest_path)


def test_proc_ingestor_exposes_generic_and_path_entry_points():
    assert callable(proc_ingestor.ingest_proc)
    assert callable(proc_ingestor.ingest_path)


def test_gateway_owns_public_ingestion_entry_points():
    assert callable(Gateway.ingest)
    assert callable(Gateway.ingest_path)


def test_dispatch_uses_generic_ingestion_expansion_hook():
    assert dispatch.expand_path is base.expand_path
    assert "ingest_python" not in vars(dispatch)


def test_router_stays_separate_from_source_implementations():
    assert "subprocess" not in vars(router)
    assert "import_module" not in vars(router)
