from dataclasses import FrozenInstanceError

import pytest

from gway.logs import LogSource, service_identity


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
