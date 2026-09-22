from pathlib import Path


def repository_root():
    return Path(__file__).resolve().parents[2]


def test_project_declares_no_runtime_dependencies():
    text = (repository_root() / "pyproject.toml").read_text(encoding="utf-8")
    assert "dependencies = []" in text


def test_core_package_has_no_requests_import():
    root = repository_root() / "gway"
    for path in root.glob("*.py"):
        assert "import requests" not in path.read_text(encoding="utf-8")



def test_core_package_does_not_depend_on_mcp_transport_implementation():
    root = repository_root() / "gway"
    violations = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8").casefold()
        if "fastmcp" in text or "sampler/mcp" in text or "sampler.mcp" in text:
            violations.append(str(path.relative_to(repository_root())))

    assert violations == []
