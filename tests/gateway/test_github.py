def test_github_operations_are_registered_as_source_read(gateway):
    expected = {
        "github.repository",
        "github.status",
        "github.branches",
        "github.branch",
        "github.commits",
        "github.commit",
        "github.file",
        "github.tree",
        "github.ref",
        "github.refs",
        "github.tags",
    }

    for name in expected:
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is False
        topics = set(operation.__gway_metadata__["topics"])
        assert {"github", "source", "read"} <= topics
