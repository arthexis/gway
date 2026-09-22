import pytest

from gway.install.service import ServiceInstallRecord, ServiceInstallState
from gway.logs import (
    LogSource,
    UnknownLogSource,
    resolve_sources,
    source_catalog,
)


def _state(tmp_path):
    state = ServiceInstallState(tmp_path)
    state.put(
        "arthexis",
        [
            ServiceInstallRecord(
                project="arthexis",
                service="web",
                backend_id="arthexis-web.service",
                backend="systemd",
            ),
            ServiceInstallRecord(
                project="arthexis",
                service="worker",
                backend_id="arthexis-worker.service",
                backend="systemd",
            ),
            ServiceInstallRecord(
                project="arthexis",
                service="beat",
                backend_id="arthexis-beat.service",
                backend="systemd",
            ),
        ],
    )
    state.put(
        "other",
        [
            ServiceInstallRecord(
                project="other",
                service="api",
                backend_id="other-api.service",
                backend="systemd",
            )
        ],
    )
    return state


def test_source_catalog_includes_gway_and_installed_sources(tmp_path):
    catalog = source_catalog(_state(tmp_path))

    assert [source.identity for source in catalog] == [
        "gway",
        "arthexis",
        "other",
        "arthexis/beat",
        "arthexis/web",
        "arthexis/worker",
        "other/api",
    ]
    assert catalog[0].kind == "gway"
    assert catalog[0].backend == "journal"
    assert catalog[0].backend_id == "gway"


def test_zero_requested_sources_selects_all_concrete_managed_sources(tmp_path):
    catalog = source_catalog(_state(tmp_path))

    resolved = resolve_sources([], catalog)

    assert [source.identity for source in resolved] == [
        "arthexis/beat",
        "arthexis/web",
        "arthexis/worker",
        "gway",
        "other/api",
    ]


def test_concrete_source_resolves_directly(tmp_path):
    catalog = source_catalog(_state(tmp_path))

    resolved = resolve_sources(["arthexis/web"], catalog)

    assert [source.identity for source in resolved] == ["arthexis/web"]


def test_project_source_expands_using_project_metadata(tmp_path):
    catalog = source_catalog(_state(tmp_path))

    resolved = resolve_sources(["arthexis"], catalog)

    assert [source.identity for source in resolved] == [
        "arthexis/beat",
        "arthexis/web",
        "arthexis/worker",
    ]


def test_overlapping_project_and_service_selection_is_deduplicated(tmp_path):
    catalog = source_catalog(_state(tmp_path))

    resolved = resolve_sources(["arthexis", "arthexis/web"], catalog)

    assert [source.identity for source in resolved] == [
        "arthexis/beat",
        "arthexis/web",
        "arthexis/worker",
    ]


def test_multiple_projects_and_gway_union_cleanly(tmp_path):
    catalog = source_catalog(_state(tmp_path))

    resolved = resolve_sources(["gway", "arthexis", "other/api"], catalog)

    assert [source.identity for source in resolved] == [
        "arthexis/beat",
        "arthexis/web",
        "arthexis/worker",
        "gway",
        "other/api",
    ]


def test_unknown_source_fails_clearly(tmp_path):
    catalog = source_catalog(_state(tmp_path))

    with pytest.raises(UnknownLogSource, match="missing") as raised:
        resolve_sources(["missing"], catalog)

    assert raised.value.identity == "missing"


def test_project_expansion_does_not_depend_on_identity_prefix():
    available = [
        LogSource(identity="alias", kind="project", project="actual"),
        LogSource(
            identity="strange-name",
            kind="service",
            project="actual",
            service="worker",
            backend="systemd",
            backend_id="actual-worker.service",
            system=False,
        ),
    ]

    resolved = resolve_sources(["alias"], available)

    assert [source.identity for source in resolved] == ["strange-name"]


def test_duplicate_catalog_identity_is_rejected():
    available = [
        LogSource(identity="same", kind="gway", backend="journal"),
        LogSource(identity="same", kind="service", backend="systemd"),
    ]

    with pytest.raises(ValueError, match="Duplicate log source identity"):
        resolve_sources([], available)


def test_gway_project_aggregate_does_not_shadow_builtin_source(tmp_path):
    state = ServiceInstallState(tmp_path)
    state.put(
        "gway",
        [
            ServiceInstallRecord(
                project="gway",
                service="worker",
                backend_id="gway-worker.service",
            )
        ],
    )

    catalog = source_catalog(state)

    assert [source.identity for source in catalog] == [
        "gway",
        "gway/worker",
    ]
    assert resolve_sources(["gway"], catalog)[0].kind == "gway"
