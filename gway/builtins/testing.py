__all__ = [
    "is_test_flag",
    "test",
    "list_flags",
]

import os


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

            class TimedResult(unittest.TextTestResult):
                def startTest(self, test):
                    super().startTest(test)
                    if getattr(gw, "timed_enabled", False):
                        self._start_time = time.perf_counter()

                def stopTest(self, test):
                    if getattr(gw, "timed_enabled", False) and hasattr(self, "_start_time"):
                        elapsed = time.perf_counter() - self._start_time
                        gw.log(f"[test] {test} took {elapsed:.3f}s")
                    super().stopTest(test)

            runner = unittest.TextTestRunner(verbosity=2, resultclass=TimedResult)
            result = runner.run(test_suite)
            gw.info(f"Test results: {str(result).strip()}")

        if cov:
            cov.stop()
            try:
                percent = cov.report(include=["gway/*"])
                gw.info(f"gway coverage: {percent:.2f}%")
                print(f"gway: {percent:.2f}%")
                projects_dir = "projects"
                if os.path.isdir(projects_dir):
                    for proj in sorted(os.listdir(projects_dir)):
                        if proj.startswith("__"):
                            continue
                        path = os.path.join(projects_dir, proj)
                        include_paths = []
                        if os.path.isdir(path):
                            include_paths = [os.path.join(os.path.abspath(path), "*")]
                        elif os.path.isfile(path) and path.endswith(".py"):
                            include_paths = [os.path.abspath(path)]
                        if include_paths:
                            try:
                                percent = cov.report(include=include_paths)
                                gw.info(f"{proj} coverage: {percent:.2f}%")
                                print(f"{proj}: {percent:.2f}%")
                            except Exception:
                                gw.warning(f"Coverage report failed for {proj}")
                total = cov.report()
                gw.info(f"Total coverage: {total:.2f}%")
                print(f"Total: {total:.2f}%")
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
