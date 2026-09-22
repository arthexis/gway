import pytest

from gway.logs import (
    gway_identity,
    project_identity,
    recipe_identity,
    service_identity,
)


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
