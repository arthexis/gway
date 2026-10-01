from pathlib import Path

from gway import Gateway
from gway.dispatch import resolve_operation
from gway.tokens import tokenize


def test_github_is_discovered_lazily_through_sampler_route():
    gateway = Gateway()

    assert not hasattr(gateway, "_github_controller")
    assert gateway.ops.resolve("github.status") is None

    resolution = resolve_operation(gateway, tokenize("github status"))

    operation = gateway.ops.resolve("github.status")
    assert resolution.operation is operation
    assert operation is not None
    assert operation.mutates is False
    assert {"github", "source", "read"} <= set(
        operation.__gway_metadata__["topics"]
    )
    assert gateway._github_controller is not None


def test_gateway_has_no_github_specific_ingestion_hook():
    source = Path("gway/gateway.py").read_text(encoding="utf-8")

    assert "githubops" not in source
    assert "GitHubController" not in source
    assert "_github_controller" not in source


def test_sampler_github_is_plain_python_capability_package():
    root = Path("sampler/github")

    assert (root / "__init__.py").is_file()
    assert (root / "github.py").is_file()
    assert (root / "githubops.py").is_file()
    assert (root / "githubcheck.py").is_file()
    assert not any(root.glob("*.rx"))
