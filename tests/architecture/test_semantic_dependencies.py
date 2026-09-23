import ast
import inspect
from pathlib import Path

from gway import Gateway


ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENT_MODULE = "gway.environment"


def _environment_imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    module_aliases = set()
    symbol_aliases = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == ENVIRONMENT_MODULE:
                    module_aliases.add(alias.asname or alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module == ENVIRONMENT_MODULE:
                for alias in node.names:
                    symbol_aliases.add(alias.asname or alias.name)
            elif node.level and node.module == "environment":
                for alias in node.names:
                    symbol_aliases.add(alias.asname or alias.name)

    return tree, module_aliases, symbol_aliases


def _direct_environment_dependencies(path, *, function_name=None):
    tree, module_aliases, symbol_aliases = _environment_imports(path)
    if not module_aliases and not symbol_aliases:
        return []

    scopes = [tree]
    if function_name is not None:
        scopes = [
            node
            for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == function_name
        ]
        if not scopes:
            return []

    violations = []
    for scope in scopes:
        for node in ast.walk(scope):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                if node.id in symbol_aliases:
                    violations.append((node.lineno, node.id))
            elif (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Name)
                and node.value.id in module_aliases
            ):
                violations.append((node.lineno, ast.unparse(node)))
    return sorted(set(violations))


def _implementation(record):
    implementation = inspect.unwrap(record.callable)
    return getattr(implementation, "__func__", implementation)


def test_registered_operations_do_not_depend_directly_on_environment_substrate():
    gateway = Gateway()
    violations = []

    for record in gateway.ops._registry.records.values():
        implementation = _implementation(record)
        path_text = inspect.getsourcefile(implementation)
        if not path_text:
            continue
        path = Path(path_text).resolve()
        if not path.is_relative_to(ROOT / "gway"):
            continue

        for lineno, expression in _direct_environment_dependencies(
            path,
            function_name=getattr(implementation, "__name__", None),
        ):
            violations.append(
                f"{record.name}: {path.relative_to(ROOT)}:{lineno}: {expression}"
            )

    assert violations == [], (
        "Registered operations must consume semantic values or explicit "
        "interoperability capabilities instead of depending directly on "
        "gway.environment:\n" + "\n".join(violations)
    )


def test_semantic_providers_do_not_depend_directly_on_environment_substrate():
    violations = []
    for path in sorted((ROOT / "gway" / "providers").rglob("*.py")):
        for lineno, expression in _direct_environment_dependencies(path):
            violations.append(
                f"{path.relative_to(ROOT)}:{lineno}: {expression}"
            )

    assert violations == [], (
        "Semantic providers must declare bindings rather than read the process "
        "environment directly:\n" + "\n".join(violations)
    )


def test_literal_environment_builtins_use_interoperability_facade():
    path = ROOT / "gway" / "builtin.py"

    assert _direct_environment_dependencies(path) == []
    text = path.read_text(encoding="utf-8")
    assert "from .interop import environment as literal_environment" in text



def test_operation_dependency_check_detects_direct_environment_symbol(tmp_path):
    path = tmp_path / "operation.py"
    path.write_text(
        "from gway.environment import process_environment\n"
        "def deploy():\n"
        "    return process_environment.get('VALUE')\n",
        encoding="utf-8",
    )

    assert _direct_environment_dependencies(path, function_name="deploy")


def test_operation_dependency_check_ignores_semantic_binding_dependency(tmp_path):
    path = tmp_path / "provider.py"
    path.write_text(
        "from gway.bindings import env\n"
        "def register(gateway):\n"
        "    gateway.bind('demo.value', env('DEMO_VALUE'))\n",
        encoding="utf-8",
    )

    assert _direct_environment_dependencies(path, function_name="register") == []
