import gway.ingestion.base as base


def test_ingestion_base_is_source_agnostic():
    names = set(base.register_operation.__code__.co_names)
    assert "subprocess" not in names
    assert "inspect" not in names


def test_ingestion_base_exposes_registration_boundary():
    assert callable(base.register_operation)
    assert callable(base.register_operations)
