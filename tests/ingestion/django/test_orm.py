from types import SimpleNamespace

import pytest

import gway.ingestion.django as django_ingestor
from gway.ingestion.base import find_ingested


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



def test_model_ingestion_discovers_single_part_natural_key(
    gateway,
    django_orm,
):
    Charger, manager = django_orm

    def get_by_natural_key(identity):
        return Charger(identity)

    manager.get_by_natural_key = get_by_natural_key
    gateway.ingest(Charger)

    record = find_ingested(gateway, ("energy", "charger"))
    assert record.metadata["natural_key"] == {
        "parameters": ("identity",),
        "arity": 1,
    }


def test_model_ingestion_discovers_composite_natural_key(
    gateway,
    django_orm,
):
    Charger, manager = django_orm

    def get_by_natural_key(vendor, model):
        return vendor, model

    manager.get_by_natural_key = get_by_natural_key
    gateway.ingest(Charger)

    record = find_ingested(gateway, ("energy", "charger"))
    assert record.metadata["natural_key"] == {
        "parameters": ("vendor", "model"),
        "arity": 2,
    }


def test_natural_key_discovery_accepts_inherited_manager_method(
    gateway,
    django_orm,
):
    Charger, original = django_orm
    manager_base = type(original).__mro__[1]

    class NaturalManager(manager_base):
        model = Charger

        def get_by_natural_key(self, identity):
            return Charger(identity)

    class SpecializedManager(NaturalManager):
        pass

    Charger._default_manager = SpecializedManager()
    gateway.ingest(Charger)

    record = find_ingested(gateway, ("energy", "charger"))
    assert record.metadata["natural_key"] == {
        "parameters": ("identity",),
        "arity": 1,
    }


def test_model_without_natural_key_has_no_natural_key_metadata(
    gateway,
    django_orm,
):
    Charger, _ = django_orm

    gateway.ingest(Charger)

    record = find_ingested(gateway, ("energy", "charger"))
    assert "natural_key" not in record.metadata


@pytest.mark.parametrize(
    "lookup",
    [
        lambda *parts: parts,
        lambda identity="default": identity,
        lambda *, identity: identity,
    ],
)
def test_unusable_natural_key_signatures_are_not_discovered(
    gateway,
    django_orm,
    lookup,
):
    Charger, manager = django_orm
    manager.get_by_natural_key = lookup

    gateway.ingest(Charger)

    record = find_ingested(gateway, ("energy", "charger"))
    assert "natural_key" not in record.metadata



def test_natural_key_selector_uses_app_qualified_model_subject(
    gateway,
    django_orm,
):
    Charger, manager = django_orm

    def get_by_natural_key(identity):
        return Charger(identity)

    manager.get_by_natural_key = get_by_natural_key
    gateway.ingest(Charger)

    selected = gateway("energy charger CHG001")

    assert isinstance(selected, Charger)
    assert selected.serial == "CHG001"
    operation = gateway.ops.resolve("energy.charger")
    assert operation is not None
    assert operation.__gway_source_kind__ == "django-natural-key"
    assert operation.__gway_metadata__["natural_key"] == {
        "parameters": ("identity",),
        "arity": 1,
    }


def test_project_indexed_natural_key_selector_gets_short_subject_alias(
    gateway,
    django_project,
    django_setup,
    django_orm,
):
    root, _ = django_project()
    Charger, manager = django_orm

    def get_by_natural_key(identity):
        return Charger(identity)

    manager.get_by_natural_key = get_by_natural_key
    django_setup(_app("energy", [Charger]))
    django_ingestor.ingest_project(gateway, root)

    selected = gateway("charger CHG002")

    assert isinstance(selected, Charger)
    assert selected.serial == "CHG002"


def test_composite_natural_key_selector_binds_all_positional_parts(
    gateway,
    django_project,
    django_setup,
    django_orm,
):
    root, _ = django_project()
    Charger, manager = django_orm

    def get_by_natural_key(site, identity):
        return Charger(f"{site}:{identity}")

    manager.get_by_natural_key = get_by_natural_key
    django_setup(_app("energy", [Charger]))
    django_ingestor.ingest_project(gateway, root)

    selected = gateway("charger MTY CHG003")

    assert selected.serial == "MTY:CHG003"


def test_natural_key_selection_can_pipe_into_model_operation(
    gateway,
    django_project,
    django_setup,
    django_orm,
):
    root, _ = django_project()
    Charger, manager = django_orm

    def get_by_natural_key(identity):
        return Charger(identity)

    @classmethod
    def reset(cls, charger, *, hard: bool = False):
        return charger.serial, hard

    manager.get_by_natural_key = get_by_natural_key
    Charger.reset = reset
    django_setup(_app("energy", [Charger]))
    django_ingestor.ingest_project(gateway, root)

    assert gateway("charger CHG004 - reset --hard") == ("CHG004", True)


def test_model_without_natural_key_is_not_directly_selectable(
    gateway,
    django_project,
    django_setup,
    django_orm,
):
    root, _ = django_project()
    Charger, _ = django_orm
    django_setup(_app("energy", [Charger]))
    django_ingestor.ingest_project(gateway, root)

    with pytest.raises(LookupError, match="Unable to resolve operation"):
        gateway("charger CHG005")
