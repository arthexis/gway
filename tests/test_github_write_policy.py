import pytest

from gway.githubops import Controller


class NoRequestClient:
    def __init__(self):
        self.calls = []

    def request(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        raise AssertionError("GitHub HTTP must not be reached")


@pytest.mark.parametrize(
    ("method", "args"),
    [
        ("set_variable", ("repo/name", "NAME", "value")),
        ("delete_variable", ("repo/name", "NAME")),
        ("set_secret", ("repo/name", "TOKEN", "secret")),
        ("delete_secret", ("repo/name", "TOKEN")),
    ],
)
def test_no_mutate_blocks_before_http(method, args):
    client = NoRequestClient()
    target = Controller(None, client=client)

    with pytest.raises(PermissionError, match="mutation is disabled"):
        getattr(target, method)(*args, mutate=False)

    assert client.calls == []


def test_g4_write_operations_are_separate_from_read(gateway):
    writes = {
        "github.set_variable",
        "github.delete_variable",
        "github.set_secret",
        "github.delete_secret",
    }
    reads = {
        "github.variable",
        "github.variables",
        "github.secret",
        "github.secrets",
        "github.secret_key",
    }

    for name in writes:
        operation = gateway.ops.resolve(name)
        assert operation.mutates is True
        topics = set(operation.__gway_metadata__["topics"])
        assert "write" in topics
        assert "read" not in topics

    for name in reads:
        operation = gateway.ops.resolve(name)
        assert operation.mutates is False
        topics = set(operation.__gway_metadata__["topics"])
        assert "read" in topics
        assert "write" not in topics
