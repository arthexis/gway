import gway.dispatch as dispatch
import gway.ingestion.base as ingestion


def test_dispatch_uses_generic_ingestion_expansion_hook():
    names = set(dispatch._expand_candidate.__code__.co_names)
    assert "expand_path" in names
    assert "ingest_python" not in names


def test_ingestion_base_exposes_lazy_expansion_boundary():
    assert callable(ingestion.find_ingested)
    assert callable(ingestion.expand_path)
