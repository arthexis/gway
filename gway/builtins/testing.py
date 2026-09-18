__all__ = [
    "coverage",
    "is_test_flag",
    "test",
    "list_flags",
]

import ast
import os
from collections import defaultdict
from pathlib import Path
from typing import Iterable


def is_test_flag(name: str) -> bool:
    """Return True if name is present in GW_TEST_FLAGS."""
    import os

    flags = os.environ.get("GW_TEST_FLAGS", "")
    active = {f.strip() for f in flags.replace(",", " ").split() if f.strip()}
    return name in active


def _is_installed() -> bool:
    """Return True if required dependencies are importable."""
    try:
        import requests  # noqa: F401
    except Exception:
        return False
    return True


def _install_requirements():
    import subprocess
    import sys

    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-e", "."])


def _normalize_filters(value: str | None) -> list[str]:
    if not value:
        return []
    tokens = [token.strip() for token in value.replace(",", " ").split() if token.strip()]
    return [token.lower() for token in tokens]


def _format_percentage(value: float | None) -> float:
    if value is None:
        return 0.0
    if value < 0:
        return 0.0
    if value > 100:
        return 100.0
    return round(value, 2)


def _format_badge_number(value: float) -> str:
    value = max(0.0, min(100.0, value))
    formatted = f"{value:.1f}".rstrip("0").rstrip(".")
    return formatted or "0"


def _badge_color(value: float) -> str:
    value = max(0.0, value)
    if value >= 95:
        return "brightgreen"
    if value >= 90:
        return "green"
    if value >= 80:
        return "yellowgreen"
    if value >= 70:
        return "yellow"
    if value >= 50:
        return "orange"
    if value > 0:
        return "red"
    return "lightgrey"


def _badge_url(value: float) -> str:
    number = _format_badge_number(value)
    color = _badge_color(value)
    return f"https://img.shields.io/badge/Coverage-{number}%25-{color}"


def _update_readme_badge(percent: float, readme_path: Path) -> tuple[bool, str]:
    badge_url = _badge_url(percent)

    try:
        content = readme_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return False, badge_url

    marker = ".. |coverage_badge| image:: "
    lines = content.splitlines()
    updated = False

    for idx, line in enumerate(lines):
        if line.strip().startswith(marker):
            indent = line[: len(line) - len(line.lstrip())]
            lines[idx] = f"{indent}{marker}{badge_url}"
            updated = True
            break

    if updated:
        readme_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    return updated, badge_url


def _summarize_records(records: Iterable[dict]) -> dict:
    records = list(records)
    if not records:
        return {"coverage": 0.0, "statements": 0, "missed": 0, "items": []}
    total_statements = sum(item["statements"] for item in records)
    total_missed = sum(item["missed"] for item in records)
    coverage = 100.0 if total_statements == 0 else (total_statements - total_missed) / total_statements * 100
    summary = {
        "coverage": _format_percentage(coverage),
        "statements": total_statements,
        "missed": total_missed,
        "items": [],
    }

    details = []
    for item in records:
        statements = item["statements"]
        missed = item["missed"]
        pct = 100.0 if statements == 0 else (statements - missed) / statements * 100
        details.append(
            {
                "name": item["name"],
                "statements": statements,
                "missed": missed,
                "coverage": _format_percentage(pct),
            }
        )

    summary["items"] = sorted(details, key=lambda x: (x["name"]))
    return summary


def _collect_functions(
    path: Path,
    module: str,
    statement_lines: set[int],
    missing_lines: set[int],
    filters: list[str],
) -> list[dict]:
    if not filters:
        return []

    try:
        source = path.read_text(encoding="utf-8")
    except OSError:
        return []

    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    functions: list[dict] = []

    def visit(node: ast.AST, parents: tuple[str, ...] = ()):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                qual_parts = parents + (child.name,)
                qual = ".".join(qual_parts)
                start = getattr(child, "lineno", None)
                end = getattr(child, "end_lineno", start)
                if start is None or end is None:
                    continue
                line_range = set(range(start, end + 1))
                statements = [line for line in statement_lines if line in line_range]
                if not statements:
                    visit(child, qual_parts)
                    continue
                missed = [line for line in missing_lines if line in line_range]
                qual_lower = qual.lower()
                if any(f in qual_lower for f in filters):
                    module_name = module.split(".", 1)[1] if module.startswith("projects.") else module
                    qualified = f"{module_name}.{qual}" if module_name else qual
                    functions.append(
                        {
                            "name": qualified,
                            "statements": len(statements),
                            "missed": len(missed),
                        }
                    )
                visit(child, qual_parts)
            elif isinstance(child, ast.ClassDef):
                visit(child, parents + (child.name,))
            else:
                visit(child, parents)

    visit(tree)
    return functions


def coverage(
    *,
    core: bool = False,
    project: str | None = None,
    function: str | None = None,
    data_file: str | None = None,
    update_readme: bool = True,
) -> dict:
    """Summarize coverage metrics for GWAY core and projects."""

    from gway import gw

    try:
        from coverage import Coverage
        from coverage.exceptions import CoverageException
    except Exception as exc:  # pragma: no cover - handled via CLI messaging
        raise RuntimeError("The 'coverage' package is required to compute coverage.") from exc

    project_filters = _normalize_filters(project)
    function_filters = _normalize_filters(function)

    repo_root = Path(__file__).resolve().parents[2]
    data_path = Path(data_file or os.environ.get("COVERAGE_FILE", repo_root / ".coverage"))

    if not data_path.exists():
        message = f"Coverage data file not found at {data_path}"
        gw.warning(message)
        return {
            "total": {"coverage": 0.0, "statements": 0, "missed": 0, "items": []},
            "filters": {"core": core, "project": project, "function": function},
            "badge": {"url": _badge_url(0.0), "updated": False},
        }

    cov = Coverage(data_file=str(data_path))
    try:
        cov.load()
    except CoverageException as exc:
        gw.warning(f"Failed to load coverage data: {exc}")
        return {
            "total": {"coverage": 0.0, "statements": 0, "missed": 0, "items": []},
            "filters": {"core": core, "project": project, "function": function},
            "badge": {"url": _badge_url(0.0), "updated": False},
        }

    records: list[dict] = []
    data = cov.get_data()

    for filename in sorted(data.measured_files()):
        path = Path(filename)
        if not path.exists():
            continue
        try:
            rel = path.resolve().relative_to(repo_root)
        except ValueError:
            continue
        if rel.suffix != ".py":
            continue
        if rel.parts and rel.parts[0] == "tests":
            continue

        module_name = ".".join(rel.with_suffix("").parts)
        if module_name.endswith(".__init__"):
            module_name = module_name[: -len(".__init__")]

        category = None
        project_name = None
        if rel.parts and rel.parts[0] == "gway":
            category = "core"
        elif rel.parts and rel.parts[0] == "projects":
            category = "project"
            if module_name.startswith("projects."):
                project_module = module_name.split(".", 1)[1]
            else:
                project_module = module_name
            project_name = project_module.split(".", 1)[0]
        else:
            continue

        if core and category != "core":
            continue

        if project_filters and category != "project":
            continue

        try:
            _, statements, _, missing, _ = cov.analysis2(str(path))
        except Exception:
            continue

        statement_lines = set(statements)
        missing_lines = set(missing)
        if not statement_lines and not function_filters:
            continue

        module_display = module_name.split(".", 1)[1] if module_name.startswith("projects.") else module_name
        record = {
            "category": category,
            "project": project_name,
            "module": module_display,
            "statements": len(statement_lines),
            "missed": len(missing_lines),
        }

        if project_filters and category == "project":
            module_lower = module_display.lower()
            rel_lower = "/".join(rel.parts).lower()
            if not any(
                filt in module_lower or filt in rel_lower or (project_name and filt in project_name.lower())
                for filt in project_filters
            ):
                continue

        if function_filters:
            record["functions"] = _collect_functions(path, module_name, statement_lines, missing_lines, function_filters)
            if not record["functions"]:
                continue
        else:
            record["functions"] = []

        records.append(record)

    formatted_records: list[dict] = []
    for record in records:
        if function_filters:
            for fn in record["functions"]:
                formatted_records.append(
                    {
                        "category": record["category"],
                        "project": record["project"],
                        "name": fn["name"],
                        "statements": fn["statements"],
                        "missed": fn["missed"],
                    }
                )
        else:
            formatted_records.append(
                {
                    "category": record["category"],
                    "project": record["project"],
                    "name": record["module"],
                    "statements": record["statements"],
                    "missed": record["missed"],
                }
            )

    core_records = [item for item in formatted_records if item["category"] == "core"]
    project_records = [item for item in formatted_records if item["category"] == "project" and item.get("project")]

    result: dict = {
        "filters": {"core": core, "project": project, "function": function},
        "total": _summarize_records(formatted_records),
    }

    if core_records:
        result["core"] = _summarize_records(core_records)

    if project_records:
        project_summary = _summarize_records(project_records)
        grouped: dict[str, list[dict]] = defaultdict(list)
        for item in project_records:
            grouped[item["project"]].append(item)
        project_details = {name: _summarize_records(items) for name, items in grouped.items()}
        project_summary["projects"] = project_details
        result["projects"] = project_summary

    total_coverage = result["total"]["coverage"]
    should_update = update_readme and not core and not project_filters and not function_filters
    badge_updated = False
    badge_url = _badge_url(total_coverage)
    if should_update:
        badge_updated, badge_url = _update_readme_badge(total_coverage, repo_root / "README.rst")
        if badge_updated:
            gw.info(f"Updated coverage badge to {total_coverage:.2f}%")

    result["badge"] = {"updated": badge_updated, "url": badge_url}
    return result


def test(
    *,
    root: str = "tests",
    filter=None,
    on_success=None,
    on_failure=None,
    coverage: bool = False,
    flags=None,
    install: bool = False,
):
    """Execute all automatically detected test suites.

    Parameters
    ----------
    root : str | os.PathLike
        Directory containing the test files. May point anywhere,
        allowing discovery from temporary locations or external
        repositories.

    If ``install`` is true, or key dependencies are missing, install
    ``requirements.txt`` and the package in editable mode before running.
    """
    from gway import gw
    import os
    import time
    import unittest
    import pathlib
    from gway.logging import use_logging

    root = os.fspath(root)

    orig_cwd = os.getcwd()
    repo_root = pathlib.Path(os.environ.get("PWD", orig_cwd)).resolve()
    os.chdir(repo_root)
    try:
        if install or not _is_installed():
            print("Installing requirements...")
            try:
                _install_requirements()
            except Exception as e:  # pragma: no cover - installation errors are fatal
                gw.warning(f"Failed to install requirements: {e}")

        if flags:
            if isinstance(flags, str):
                flag_list = [f.strip() for f in flags.replace(',', ' ').split() if f.strip()]
            else:
                flag_list = list(flags)
            os.environ['GW_TEST_FLAGS'] = ','.join(flag_list)
            gw.testing_flags = set(flag_list)
        else:
            env_flags = os.environ.get('GW_TEST_FLAGS', '')
            gw.testing_flags = {f.strip() for f in env_flags.replace(',', ' ').split() if f.strip()}

        cov = None
        if coverage:
            try:
                from coverage import Coverage
                cov = Coverage()
                cov.start()
            except Exception as e:
                gw.warning(f"Coverage requested but failed to initialize: {e}")

        log_path = os.path.join("logs", "test.log")

        with use_logging(
            logfile="test.log",
            logdir="logs",
            prog_name="gway",
            debug=getattr(gw, "debug", False),
            backup_count=0,
            verbose=getattr(gw, "verbose", False),
        ):
            print("Running the test suite...")

            test_loader = unittest.TestLoader()
            if filter:
                pattern = f"test*{filter}*.py"
            else:
                pattern = "test*.py"

            test_suite = test_loader.discover(root, pattern=pattern)

            orig_resource = gw.resource
            orig_abort = gw.abort

            class TimedResult(unittest.TextTestResult):
                def startTest(self, test):
                    gw.resource = orig_resource
                    gw.abort = orig_abort
                    super().startTest(test)
                    if getattr(gw, "timed_enabled", False):
                        self._start_time = time.perf_counter()
                
                def stopTest(self, test):
                    gw.resource = orig_resource
                    if getattr(gw, "timed_enabled", False) and hasattr(self, "_start_time"):
                        elapsed = time.perf_counter() - self._start_time
                        gw.log(f"[test] {test} took {elapsed:.3f}s")
                    # Restore gw helpers possibly patched by tests
                    gw.abort = orig_abort
                    gw.resource = orig_resource
                    super().stopTest(test)

            runner = unittest.TextTestRunner(verbosity=2, resultclass=TimedResult)
            result = runner.run(test_suite)
            gw.info(f"Test results: {str(result).strip()}")

        if cov:
            cov.stop()
            try:
                cov.save()
            except Exception:
                pass
            try:
                summary = coverage(data_file=cov.config.data_file)
                core_summary = summary.get("core")
                projects_summary = summary.get("projects", {})
                if core_summary:
                    print(f"gway: {core_summary['coverage']:.2f}%")
                project_details = projects_summary.get("projects", {})
                for proj_name in sorted(project_details):
                    print(f"{proj_name}: {project_details[proj_name]['coverage']:.2f}%")
                print(f"Total: {summary['total']['coverage']:.2f}%")
            except Exception as e:
                gw.warning(f"Coverage report failed: {e}")

        if result.wasSuccessful() and on_success == "clear":
            if os.path.exists(log_path):
                os.remove(log_path)

        if not result.wasSuccessful() and on_failure == "abort":
            gw.abort(f"Tests failed with --abort flag. Results: {str(result).strip()}")

        return result.wasSuccessful()
    finally:
        os.chdir(orig_cwd)


def list_flags(root: str = "tests") -> dict[str, list[str]]:
    """Return mapping of flags to tests referencing them.

    Parameters
    ----------
    root : str | os.PathLike
        Base directory to scan for tests.
    """
    import os
    import re

    root = os.fspath(root)

    flag_pat = re.compile(r"is_test_flag\([\"']([^\"']+)[\"']\)")
    def_pat = re.compile(r"\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)")
    result: dict[str, list[str]] = {}

    for dirpath, _, files in os.walk(root):
        for fname in files:
            if not fname.endswith(".py"):
                continue
            path = os.path.join(dirpath, fname)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
            except Exception:
                continue
            for i, line in enumerate(lines):
                m = flag_pat.search(line)
                if not m:
                    continue
                flag = m.group(1)
                test_name = None
                for j in range(i + 1, len(lines)):
                    match = def_pat.match(lines[j])
                    if match:
                        test_name = match.group(1)
                        break
                if test_name:
                    result.setdefault(flag, []).append(f"{fname}::{test_name}")

    return {k: sorted(v) for k, v in sorted(result.items())}
