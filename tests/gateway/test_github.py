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
        "github.pulls",
        "github.pull",
        "github.reviews",
        "github.comments",
        "github.issues",
        "github.issue",
        "github.workflows",
        "github.workflow",
        "github.runs",
        "github.run",
        "github.jobs",
        "github.checks",
        "github.releases",
        "github.release",
        "github.variables",
        "github.variable",
        "github.secrets",
        "github.secret",
    }

    for name in expected:
        operation = gateway.ops.resolve(name)
        assert operation is not None
        assert operation.mutates is False
        topics = set(operation.__gway_metadata__["topics"])
        assert {"github", "source", "read"} <= topics
