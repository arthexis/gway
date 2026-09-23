import ast
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
ALLOWED = {ROOT / "gway" / "environment.py"}
_DIRECT_ENVIRONMENT_ATTRIBUTES = {"environ", "getenv"}


def _is_import_os(node):
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "__import__"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "os"
    )


def _environment_accesses_source(source, *, filename="<architecture-fixture>"):
    tree = ast.parse(source, filename=filename)
    os_aliases = set()
    direct_aliases = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "os":
                    os_aliases.add(alias.asname or "os")
        elif isinstance(node, ast.ImportFrom) and node.module == "os":
            for alias in node.names:
                if alias.name in _DIRECT_ENVIRONMENT_ATTRIBUTES:
                    direct_aliases.add(alias.asname or alias.name)

    # Follow simple module aliases so "platform = os; platform.environ" cannot
    # sidestep the architectural boundary.
    changed = True
    while changed:
        changed = False
        for node in ast.walk(tree):
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            value = node.value
            is_os = (
                isinstance(value, ast.Name) and value.id in os_aliases
            ) or _is_import_os(value)
            if not is_os:
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and target.id not in os_aliases:
                    os_aliases.add(target.id)
                    changed = True

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in _DIRECT_ENVIRONMENT_ATTRIBUTES:
            if (
                isinstance(node.value, ast.Name) and node.value.id in os_aliases
            ) or _is_import_os(node.value):
                violations.append((node.lineno, ast.unparse(node)))
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load) and node.id in direct_aliases:
                violations.append((node.lineno, node.id))
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value in _DIRECT_ENVIRONMENT_ATTRIBUTES
        ):
            target = node.args[0]
            if (
                isinstance(target, ast.Name) and target.id in os_aliases
            ) or _is_import_os(target):
                violations.append((node.lineno, ast.unparse(node)))

    return sorted(set(violations))


def _environment_accesses(path):
    return _environment_accesses_source(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )


def test_direct_process_environment_access_is_centralized():
    violations = []
    for root_name in ("gway", "sampler"):
        for path in sorted((ROOT / root_name).rglob("*.py")):
            if path in ALLOWED:
                continue
            for lineno, expression in _environment_accesses(path):
                violations.append(
                    f"{path.relative_to(ROOT)}:{lineno}: {expression}"
                )

    assert violations == [], (
        "Direct process-environment access must go through gway.environment:\n"
        + "\n".join(violations)
    )


@pytest.mark.parametrize(
    "source",
    [
        "import os\nos.environ['TOKEN']\n",
        "import os as system\nsystem.getenv('TOKEN')\n",
        "from os import environ\nenviron.get('TOKEN')\n",
        "from os import getenv as read_env\nread_env('TOKEN')\n",
        "import os\nplatform = os\nplatform.environ.get('TOKEN')\n",
        "__import__('os').environ.get('TOKEN')\n",
        "import os\ngetattr(os, 'environ').get('TOKEN')\n",
        "getattr(__import__('os'), 'getenv')('TOKEN')\n",
    ],
)
def test_environment_boundary_detects_representative_bypasses(source):
    assert _environment_accesses_source(source)


@pytest.mark.parametrize(
    "source",
    [
        "import os\nos.path.join('a', 'b')\n",
        "import os\nvalue = os.name\n",
        "from os import path\npath.join('a', 'b')\n",
    ],
)
def test_environment_boundary_allows_unrelated_os_dependencies(source):
    assert _environment_accesses_source(source) == []
