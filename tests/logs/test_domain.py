from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest

from gway.logs import (
    LogRecord,
    LogSource,
    gway_identity,
    project_identity,
    recipe_identity,
    service_identity,
)


def test_log_record_requires_timezone_aware_timestamp():
    with pytest.raises(ValueError, match="timezone-aware"):
        LogRecord(
            timestamp=datetime(2026, 9, 22, 12, 0),
            source="gway",
            message="hello",
        )


def test_log_record_is_immutable_and_copies_metadata():
    metadata = {"backend": "journal"}
    record = LogRecord(
        timestamp=datetime(2026, 9, 22, 12, 0, tzinfo=timezone.utc),
        source="gway",
        message="hello",
        metadata=metadata,
    )

    metadata["backend"] = "changed"

    assert record.metadata["backend"] == "journal"
    with pytest.raises(TypeError):
        record.metadata["backend"] = "changed"
    with pytest.raises(FrozenInstanceError):
        record.message = "changed"


def test_source_is_descriptive_and_immutable():
    source = LogSource(
        identity="arthexis/web",
        kind="service",
        project="arthexis",
        service="web",
        backend="systemd",
        backend_id="arthexis-web.service",
        system=False,
    )

    assert source.identity == "arthexis/web"
    assert source.backend_id == "arthexis-web.service"
    assert not hasattr(source, "read")
    assert not hasattr(source, "tail")
    with pytest.raises(FrozenInstanceError):
        source.backend_id = "other.service"


def test_canonical_source_identities():
    assert gway_identity() == "gway"
    assert project_identity(" arthexis ") == "arthexis"
    assert service_identity("arthexis", "web") == "arthexis/web"
    assert recipe_identity("deploy") == "recipe/deploy"


@pytest.mark.parametrize(
    ("function", "arguments"),
    [
        (project_identity, ("",)),
        (project_identity, ("foo/bar",)),
        (service_identity, ("arthexis", "")),
        (service_identity, ("arthexis", "web/api")),
        (recipe_identity, ("deploy/nightly",)),
    ],
)
def test_identity_segments_reject_ambiguous_values(function, arguments):
    with pytest.raises(ValueError):
        function(*arguments)


def test_backend_identity_does_not_define_logical_identity():
    first = LogSource(
        identity=service_identity("arthexis", "web"),
        kind="service",
        backend="systemd",
        backend_id="arthexis-web.service",
    )
    second = LogSource(
        identity=service_identity("arthexis", "web"),
        kind="service",
        backend="other",
        backend_id="completely-different",
    )

    assert first.identity == second.identity == "arthexis/web"
