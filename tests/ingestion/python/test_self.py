import gway

from gway.dispatch import resolve_operation


def test_gway_can_ingest_itself_without_recursive_expansion(gateway):
    wrapped = gateway.ingest(gway)

    assert wrapped == []
    assert gateway.ops.resolve("gway.gateway") is None
    assert gateway.ops.resolve("gway.gw") is not None
    assert gateway.ops.resolve("gway.gateway.wrap") is None
    assert gateway.ops.resolve("gway.gw.chain") is None


def test_gway_self_ingestion_expands_requested_branches_with_jiti(gateway):
    gateway.ingest(gway)

    resolve_operation(gateway, ["gway", "Installation", "with_installed_at"])
    resolve_operation(gateway, ["gway", "gw", "chain"])

    assert gateway.ops.resolve("gway.installation.with_installed_at") is not None
    assert gateway.ops.resolve("gway.gw.chain") is not None


def test_gway_self_ingestion_concrete_module_shadows_equivalent_class(gateway):
    gateway.ingest(gway)

    assert gateway.ops.resolve("gway.gateway.wrap") is None
    module_record = next(
        record
        for record in gateway._ingested.values()
        if ("gway", "gateway") in record.paths
    )
    assert module_record.value is gway.gateway


def test_gway_self_ingestion_reuses_known_object_identity(gateway):
    gateway.ingest(gway)

    module_record = gateway._ingested[id(gway)]
    gw_record = gateway._ingested[id(gway.gw)]

    gateway.ingest(gway)

    assert gateway._ingested[id(gway)] is module_record
    assert gateway._ingested[id(gway.gw)] is gw_record
