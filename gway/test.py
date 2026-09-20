"""Built-in test-suite inspection and execution operations."""

import ast as _ast
from pathlib import Path as _Path
import re as _re
import subprocess as _subprocess
import sys as _sys


def _test_root(root="tests"):
    path = _Path(root).expanduser()
    if not path.is_dir():
        raise ValueError(f"Test root is not a directory: {path}")
    return path.resolve()


def _selected_root(root="tests", package=None):
    base = _test_root(root)
    if package is None:
        return base

    candidate = _Path(package)
    if candidate.is_absolute():
        selected = candidate
    elif candidate.parts and candidate.parts[0] == base.name:
        selected = base.parent / candidate
    else:
        selected = base / candidate

    selected = selected.resolve()
    try:
        selected.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"Test selection must stay inside {base}") from exc
    if not selected.exists():
        raise ValueError(f"Test selection does not exist: {selected}")
    return selected


def _files(root="tests", package=None):
    selected = _selected_root(root, package)
    if selected.is_file():
        return [selected] if selected.suffix == ".py" else []
    return sorted(
        path
        for path in selected.rglob("*.py")
        if path.name != "__init__.py" and not path.name.startswith("conftest")
    )


def _functions(path):
    tree = _ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node.name
        for node in tree.body
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]


def _inventory(root="tests", package=None):
    base = _test_root(root)
    records = []
    for path in _files(root, package):
        names = _functions(path)
        if not names:
            continue
        relative = path.relative_to(base)
        package_name = relative.parts[0] if len(relative.parts) > 1 else "(root)"
        records.append(
            {
                "path": relative.as_posix(),
                "package": package_name,
                "functions": names,
                "count": len(names),
            }
        )
    return records


def summary(root="tests", package=None):
    """Return a static summary of discovered test functions.

    Args:
        root: Test-suite directory used as the discovery boundary.
        package: Optional file or subdirectory to inspect within the test root.
    """
    records = _inventory(root, package)
    packages = {}
    for record in records:
        packages[record["package"]] = (
            packages.get(record["package"], 0) + record["count"]
        )
    return {
        "functions": sum(record["count"] for record in records),
        "modules": len(records),
        "packages": dict(sorted(packages.items())),
    }


def __main__(root="tests", package=None):
    """Return the default test-suite summary.

    Args:
        root: Test-suite directory used as the discovery boundary.
        package: Optional file or subdirectory to inspect within the test root.
    """
    return summary(root=root, package=package)


def count(package=None, root="tests", by=None):
    """Count discovered test functions.

    Args:
        package: Optional file or subdirectory to inspect within the test root.
        root: Test-suite directory used as the discovery boundary.
        by: Optional grouping, either "package" or "module".
    """
    records = _inventory(root, package)
    if by is None:
        return sum(record["count"] for record in records)
    if by == "package":
        grouped = {}
        for record in records:
            grouped[record["package"]] = (
                grouped.get(record["package"], 0) + record["count"]
            )
        return dict(sorted(grouped.items()))
    if by == "module":
        return {record["path"]: record["count"] for record in records}
    raise ValueError("--by must be 'package' or 'module'")


def list(package=None, root="tests"):
    """List discovered test functions with provenance.

    Args:
        package: Optional file or subdirectory to inspect within the test root.
        root: Test-suite directory used as the discovery boundary.
    """
    return [
        {
            "package": record["package"],
            "module": record["path"],
            "name": name,
        }
        for record in _inventory(root, package)
        for name in record["functions"]
    ]


def _pytest_args(package=None, root="tests"):
    selected = _selected_root(root, package)
    return [_sys.executable, "-m", "pytest", str(selected)]


def collect(package=None, root="tests"):
    """Ask pytest how many executable cases it would collect.

    Args:
        package: Optional file or subdirectory passed to pytest for collection.
        root: Test-suite directory used as the selection boundary.
    """
    command = [*_pytest_args(package, root), "--collect-only", "-q"]
    completed = _subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
    )
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    matches = _re.findall(r"(\d+)\s+(?:tests?|items?)\s+collected", output)
    collected = int(matches[-1]) if matches else None
    return {
        "collected": collected,
        "returncode": completed.returncode,
        "command": command,
    }


def run(
    package=None,
    root="tests",
    keyword=None,
    failed=False,
    verbose=False,
):
    """Run tests through pytest and return its exit status.

    Args:
        package: Optional file or subdirectory to execute within the test root.
        root: Test-suite directory used as the selection boundary.
        keyword: Pytest -k expression used to filter collected tests.
        failed: Re-run only tests remembered by pytest as last failures.
        verbose: Ask pytest for its verbose test-reporting mode.
    """
    command = _pytest_args(package, root)
    if keyword:
        command.extend(["-k", keyword])
    if failed:
        command.append("--lf")
    if verbose:
        command.append("-v")
    return _subprocess.run(command, check=False).returncode
