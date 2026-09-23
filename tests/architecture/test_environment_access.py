import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ALLOWED = {ROOT / 'gway' / 'environment.py'}


def _environment_accesses(path):
    tree = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    os_aliases = set()
    direct_aliases = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == 'os':
                    os_aliases.add(alias.asname or 'os')
        elif isinstance(node, ast.ImportFrom) and node.module == 'os':
            for alias in node.names:
                if alias.name in {'environ', 'getenv'}:
                    direct_aliases.add(alias.asname or alias.name)

    violations = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            if (
                isinstance(node.value, ast.Name)
                and node.value.id in os_aliases
                and node.attr in {'environ', 'getenv'}
            ):
                violations.append((node.lineno, ast.unparse(node)))
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load) and node.id in direct_aliases:
                violations.append((node.lineno, node.id))
    return violations


def test_direct_process_environment_access_is_centralized():
    violations = []
    for root_name in ('gway', 'sampler'):
        for path in sorted((ROOT / root_name).rglob('*.py')):
            if path in ALLOWED:
                continue
            for lineno, expression in _environment_accesses(path):
                violations.append(
                    f'{path.relative_to(ROOT)}:{lineno}: {expression}'
                )

    assert violations == [], (
        'Direct process-environment access must go through gway.environment:\n'
        + '\n'.join(violations)
    )
