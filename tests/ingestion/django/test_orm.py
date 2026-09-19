import pytest

import gway.ingestion.django as django_ingestor
from gway.ingestion.base import find_ingested


def _manager_returns(manager, name, value):
    """Install one simple collection-returning manager operation."""
    setattr(type(manager), name, lambda self: value)


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

    assert gateway("all chargers") == ["all"]
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
    django_mount,
    django_orm,
):
    Charger, _ = django_orm
    django_mount(Charger)

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
    django_mount,
    django_orm,
):
    Charger, manager = django_orm

    def get_by_natural_key(identity):
        return Charger(identity)

    manager.get_by_natural_key = get_by_natural_key
    django_mount(Charger)

    selected = gateway("charger CHG002")

    assert isinstance(selected, Charger)
    assert selected.serial == "CHG002"


def test_composite_natural_key_selector_binds_all_positional_parts(
    gateway,
    django_mount,
    django_orm,
):
    Charger, manager = django_orm

    def get_by_natural_key(site, identity):
        return Charger(f"{site}:{identity}")

    manager.get_by_natural_key = get_by_natural_key
    django_mount(Charger)

    selected = gateway("charger MTY CHG003")

    assert selected.serial == "MTY:CHG003"


def test_natural_key_selection_can_pipe_into_model_operation(
    gateway,
    django_mount,
    django_orm,
):
    Charger, manager = django_orm

    def get_by_natural_key(identity):
        return Charger(identity)

    @classmethod
    def reset(cls, charger, *, hard: bool = False):
        return charger.serial, hard

    manager.get_by_natural_key = get_by_natural_key
    Charger.reset = reset
    django_mount(Charger)

    assert gateway("charger CHG004 - reset --hard") == ("CHG004", True)


def test_model_without_natural_key_is_not_directly_selectable(
    gateway,
    django_mount,
    django_orm,
):
    Charger, _ = django_orm
    django_mount(Charger)

    with pytest.raises(LookupError, match="Unable to resolve operation"):
        gateway("charger CHG005")


def test_singular_django_manager_result_unwraps_exactly_one_match(
    gateway,
    django_orm,
):
    Charger, manager = django_orm

    _manager_returns(manager, "connected", [Charger("CHG001")])
    gateway.ingest(Charger)

    selected = gateway("connected charger")

    assert isinstance(selected, Charger)
    assert selected.serial == "CHG001"
    assert gateway.last is selected
    assert gateway.results["charger"] is selected


def test_plural_django_manager_result_preserves_collection(
    gateway,
    django_orm,
):
    Charger, manager = django_orm

    chargers = [Charger("CHG001"), Charger("CHG002")]

    _manager_returns(manager, "connected", chargers)
    gateway.ingest(Charger)

    selected = gateway("connected chargers")

    assert selected is chargers
    assert gateway.last is chargers
    assert gateway.results["charger"] is chargers


def test_singular_django_manager_result_rejects_zero_matches(
    gateway,
    django_orm,
):
    Charger, manager = django_orm

    _manager_returns(manager, "connected", [])
    gateway.ingest(Charger)

    with pytest.raises(LookupError, match="No charger matched"):
        gateway("connected charger")

    assert gateway.last is None
    assert "charger" not in gateway.results.maps[0]


def test_singular_django_manager_result_rejects_multiple_matches(
    gateway,
    django_orm,
):
    Charger, manager = django_orm

    _manager_returns(
        manager,
        "connected",
        [Charger("CHG001"), Charger("CHG002")],
    )
    gateway.ingest(Charger)

    with pytest.raises(LookupError, match="Expected one charger"):
        gateway("connected charger")

    assert gateway.last is None
    assert "charger" not in gateway.results.maps[0]


def test_failed_cardinality_restores_previous_semantic_result(
    gateway,
    django_orm,
):
    Charger, manager = django_orm
    previous = Charger("PREVIOUS")
    gateway.results.insert("charger", previous)

    _manager_returns(
        manager,
        "connected",
        [Charger("CHG001"), Charger("CHG002")],
    )
    gateway.ingest(Charger)

    with pytest.raises(LookupError, match="Expected one charger"):
        gateway("connected charger")

    assert gateway.last is previous
    assert gateway.results["charger"] is previous


def test_singular_cardinality_checks_only_first_two_lazy_results(
    gateway,
    django_orm,
):
    Charger, manager = django_orm

    class LazyResults:
        def __init__(self):
            self.slices = []

        def __getitem__(self, key):
            self.slices.append(key)
            return [Charger("CHG001"), Charger("CHG002")][key]

        def __iter__(self):
            raise AssertionError("full collection should not be iterated")

    lazy = LazyResults()

    _manager_returns(manager, "connected", lazy)
    gateway.ingest(Charger)

    with pytest.raises(LookupError, match="Expected one charger"):
        gateway("connected charger")

    assert lazy.slices == [slice(None, 2, None)]


def test_direct_plural_collection_rejects_singular_model_operation(
    gateway,
    django_orm,
):
    Charger, manager = django_orm
    chargers = [Charger("CHG001"), Charger("CHG002")]

    _manager_returns(manager, "charging", chargers)

    @classmethod
    def reset(cls, charger):
        raise AssertionError("reset must not be invoked for a charger collection")

    Charger.reset = reset
    gateway.ingest(Charger)

    with pytest.raises(TypeError, match="Collection of charger"):
        gateway("charging chargers - reset")


def test_direct_plural_collection_accepts_explicit_collection_consumer(
    gateway,
    django_orm,
):
    Charger, manager = django_orm
    chargers = [Charger("CHG001"), Charger("CHG002")]

    _manager_returns(manager, "charging", chargers)

    @classmethod
    def summarize(cls, chargers):
        return [charger.serial for charger in chargers]

    Charger.summarize = summarize
    gateway.ingest(Charger)

    assert gateway("charging chargers - summarize") == ["CHG001", "CHG002"]


def test_direct_plural_collection_accepts_collection_annotation(
    gateway,
    django_orm,
):
    Charger, manager = django_orm
    chargers = [Charger("CHG001"), Charger("CHG002")]

    _manager_returns(manager, "charging", chargers)

    @classmethod
    def summarize(cls, items: list):
        return [charger.serial for charger in items]

    Charger.summarize = summarize
    gateway.ingest(Charger)

    assert gateway("charging chargers - summarize") == ["CHG001", "CHG002"]


def test_project_indexed_natural_key_and_cardinality_work_together(
    gateway,
    django_mount,
    django_orm,
):
    Charger, manager = django_orm
    fleet = [Charger("CHG001"), Charger("CHG002")]

    def get_by_natural_key(identity):
        for charger in fleet:
            if charger.serial == identity:
                return charger
        raise LookupError(identity)

    _manager_returns(manager, "connected", fleet)

    @classmethod
    def reset(cls, charger, *, hard: bool = False):
        return {"identity": charger.serial, "hard": hard}

    manager.get_by_natural_key = get_by_natural_key
    Charger.reset = reset

    django_mount(Charger)

    selected = gateway("charger CHG001")
    assert selected is fleet[0]

    all_connected = gateway("connected chargers")
    assert all_connected is fleet

    with pytest.raises(LookupError, match="Expected one charger"):
        gateway("connected charger")

    assert gateway("charger CHG002 - reset --hard") == {
        "identity": "CHG002",
        "hard": True,
    }


def test_project_indexed_composite_key_and_plural_query_coexist(
    gateway,
    django_mount,
    django_orm,
):
    Charger, manager = django_orm
    fleet = [
        Charger("MTY:CHG001"),
        Charger("MTY:CHG002"),
        Charger("GDL:CHG001"),
    ]

    def get_by_natural_key(site, identity):
        serial = f"{site}:{identity}"
        for charger in fleet:
            if charger.serial == serial:
                return charger
        raise LookupError(serial)

    _manager_returns(manager, "connected", fleet[:2])

    manager.get_by_natural_key = get_by_natural_key

    django_mount(Charger)

    assert gateway("charger MTY CHG002").serial == "MTY:CHG002"
    assert [charger.serial for charger in gateway("connected chargers")] == [
        "MTY:CHG001",
        "MTY:CHG002",
    ]


def test_project_indexed_plural_query_rejects_singular_domain_action(
    gateway,
    django_mount,
    django_orm,
):
    Charger, manager = django_orm
    fleet = [Charger("CHG001"), Charger("CHG002")]

    _manager_returns(manager, "connected", fleet)

    @classmethod
    def reset(cls, charger):
        raise AssertionError("collection fan-out must not happen")

    Charger.reset = reset

    django_mount(Charger)

    with pytest.raises(TypeError, match="Collection of charger"):
        gateway("connected chargers - reset")


def test_project_indexed_plural_query_accepts_collection_consumer(
    gateway,
    django_mount,
    django_orm,
):
    Charger, manager = django_orm
    fleet = [Charger("CHG001"), Charger("CHG002")]

    _manager_returns(manager, "connected", fleet)

    @classmethod
    def summarize(cls, chargers):
        return tuple(charger.serial for charger in chargers)

    Charger.summarize = summarize

    django_mount(Charger)

    assert gateway("connected chargers - summarize") == (
        "CHG001",
        "CHG002",
    )
