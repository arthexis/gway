
__all__ = [
    "is_test_flag",
    "test",
]


def is_test_flag(name: str) -> bool:
    """Return True if name is present in GW_TEST_FLAGS."""
    import os

    flags = os.environ.get("GW_TEST_FLAGS", "")
    active = {f.strip() for f in flags.replace(",", " ").split() if f.strip()}
    return name in active


def test(*, root: str = "tests", filter=None, on_success=None, on_failure=None, coverage: bool = False, flags=None):
    """Execute all automatically detected test suites."""
    from gway import gw
    import os
    import time
    import unittest
    from gway.logging import use_logging

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

        def is_test_file(file):
            if filter:
                return file.endswith('.py') and filter in file
            return file.endswith('.py') and not file.startswith('_')

        test_files = [
            os.path.join(root, f) for f in os.listdir(root)
            if is_test_file(f)
        ]

        test_loader = unittest.defaultTestLoader
        test_suite = unittest.TestSuite()

        for test_file in test_files:
            test_suite.addTests(test_loader.discover(
                os.path.dirname(test_file), pattern=os.path.basename(test_file)))

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
