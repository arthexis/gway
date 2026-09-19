from types import SimpleNamespace

import gway.ingestion.django as django_ingestor


def _app(label, models):
    return SimpleNamespace(
        label=label,
        get_models=lambda: list(models),
    )


def test_direct_model_ingestion_exposes_manager_operations_on_model_subject(
    gateway,
    django_orm,
):
    Charger, _ = django_orm

    gateway.ingest(Charger)

    assert gateway("filter charger --status online") == {"status": "online"}
    operation = gateway.ops.resolve("energy.charger.filter")
    assert operation is not None
    assert operation.__gway_source_kind__ == "django-manager"
    assert operation.__gway_subject__ == "charger"


def test_direct_model_ingestion_exposes_class_methods_on_model_subject(
    gateway,
    django_orm,
):
    Charger, _ = django_orm

    gateway.ingest(Charger)

    assert gateway("describe charger") == "charger-model"
    assert gateway.ops.resolve("energy.charger.describe") is not None


def test_direct_manager_ingestion_infers_its_model_subject(
    gateway,
    django_orm,
):
    _, manager = django_orm

    gateway.ingest(manager)

    assert gateway("all charger") == ["all"]
    assert gateway.ops.resolve("energy.charger.all") is not None


def test_direct_model_instance_ingestion_exposes_bound_methods_and_context(
    gateway,
    django_orm,
):
    Charger, _ = django_orm
    charger = Charger("CHG001")

    gateway.ingest(charger)

    assert gateway.context["charger"] is charger
    assert gateway("custom charger test") == "CHG001:test"
    assert gateway.ops.resolve("energy.charger.custom") is not None


def test_project_indexed_model_expands_manager_surface_on_first_resolution(
    gateway,
    django_project,
    django_setup,
    django_orm,
):
    root, _ = django_project()
    Charger, _ = django_orm
    django_setup(_app("energy", [Charger]))

    django_ingestor.ingest_project(gateway, root)

    assert gateway.ops.resolve("energy.charger.filter") is None
    assert gateway("filter charger --site MTY") == {"site": "MTY"}
    assert gateway.ops.resolve("energy.charger.filter") is not None


def test_django_orm_sources_are_detected_without_explicit_kind(django_orm):
    Charger, manager = django_orm

    assert django_ingestor.source_kind(Charger) == "model"
    assert django_ingestor.source_kind(Charger()) == "instance"
    assert django_ingestor.source_kind(manager) == "manager"


def test_model_operations_retain_app_qualified_canonical_paths(
    gateway,
    django_orm,
):
    Charger, _ = django_orm

    gateway.ingest(Charger)

    assert gateway.ops.resolve("energy.charger.filter") is not None
    assert gateway.ops.resolve_pair("filter", "charger") is not None
