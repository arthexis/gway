import ast
from pathlib import Path

from gway.environment import BACKEND_ENVIRONMENT


ROOT = Path(__file__).resolve().parents[2]


def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.level:
                imported.add(f"gway.{node.module}")
            else:
                imported.add(node.module)
    return imported


def test_dns_operation_has_no_physical_configuration_dependencies():
    imports = _imports(ROOT / "gway" / "dns.py")

    assert imports.isdisjoint(
        {
            "gway.environment",
            "gway.bindings",
            "gway.secrets",
            "gway.providers.godaddy",
        }
    )


def test_secrets_root_environment_is_backend_configuration():
    assert "GWAY_SECRETS_DIR" in BACKEND_ENVIRONMENT
