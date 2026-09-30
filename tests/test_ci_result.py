import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from gway.outcome import ExitResult, current_exit_code, reset_exit_code


def _load_ci_companion():
    path = Path("sampler/ci/__main__.py").resolve()
    spec = importlib.util.spec_from_file_location("gway_ci_companion_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ci_report = _load_ci_companion()


def _junit(*, failures=0, errors=0, skipped=0, message="expected 3, got 4"):
    tests = 3
    cases = [
        '<testcase classname="tests.test_ok" name="test_one" file="tests/test_ok.py"/>',
        '<testcase classname="tests.test_ok" name="test_two" file="tests/test_ok.py"/>',
    ]
    if failures:
        cases.append(
            '<testcase classname="tests.test_bad" name="test_bad" file="tests/test_bad.py">'
            f'<failure type="AssertionError" message="{message}">trace</failure>'
            '</testcase>'
        )
    elif errors:
        cases.append(
            '<testcase classname="tests.test_bad" name="test_bad" file="tests/test_bad.py">'
            '<error type="RuntimeError" message="boom">trace</error>'
            '</testcase>'
        )
    elif skipped:
        cases.append(
            '<testcase classname="tests.test_skip" name="test_skip" file="tests/test_skip.py">'
            '<skipped/>'
            '</testcase>'
        )
    else:
        cases.append(
            '<testcase classname="tests.test_ok" name="test_three" file="tests/test_ok.py"/>'
        )
    return (
        f'<testsuites><testsuite tests="{tests}" failures="{failures}" errors="{errors}" '
        f'skipped="{skipped}" time="1.25">{"".join(cases)}</testsuite></testsuites>'
    )


def test_exit_result_keeps_exit_status_out_of_public_mapping():
    reset_exit_code()
    result = ExitResult({"state": "failed"}, exit_code=7)
    assert dict(result) == {"state": "failed"}
    assert current_exit_code() == 7


def test_ci_report_returns_structured_pass(monkeypatch):
    monkeypatch.setattr(
        ci_report,
        "validate_recipes",
        lambda runtime, target: {
            "target": "/sampler",
            "recipes": 10,
            "errors": 0,
            "warnings": 0,
            "findings": [],
        },
    )

    def fake_run(command, check=False):
        junit = command[command.index("--junitxml") + 1]
        with open(junit, "w", encoding="utf-8") as stream:
            stream.write(_junit())
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(ci_report.subprocess, "run", fake_run)
    result = ci_report.report(workers=0, durations=None)

    assert result["state"] == "passed"
    assert result["phase"] == "complete"
    assert result["validation"]["state"] == "passed"
    assert result["tests"]["passed"] == 3
    assert result["tests"]["failed"] == 0
    assert result.exit_code == 0


def test_ci_report_returns_structured_failure_with_nonzero_status(monkeypatch):
    monkeypatch.setattr(
        ci_report,
        "validate_recipes",
        lambda runtime, target: {
            "target": "/sampler",
            "recipes": 10,
            "errors": 0,
            "warnings": 0,
            "findings": [],
        },
    )

    def fake_run(command, check=False):
        junit = command[command.index("--junitxml") + 1]
        with open(junit, "w", encoding="utf-8") as stream:
            stream.write(_junit(failures=1))
        return SimpleNamespace(returncode=1)

    monkeypatch.setattr(ci_report.subprocess, "run", fake_run)
    result = ci_report.report(workers=0, durations=None)

    assert result["state"] == "failed"
    assert result["phase"] == "tests"
    assert result["tests"]["failed"] == 1
    assert result["tests"]["failures"] == [
        {
            "id": "tests/test_bad.py::test_bad",
            "category": "assertion",
            "summary": "expected 3, got 4",
        }
    ]
    assert result.exit_code == 1


def test_ci_report_validation_failure_does_not_run_tests(monkeypatch):
    def fail_validation(runtime, target):
        raise ci_report.RecipeValidationError("bad recipe")

    monkeypatch.setattr(ci_report, "validate_recipes", fail_validation)
    monkeypatch.setattr(
        ci_report.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("pytest ran")),
    )

    result = ci_report.report(workers=0, durations=None)
    assert result["state"] == "failed"
    assert result["phase"] == "validation"
    assert result["tests"] is None
    assert result.exit_code == 1


def test_cli_resolves_ci_report_without_running_it():
    completed = subprocess.run(
        [sys.executable, "-m", "gway", "resolve", "ci", "report", "--json"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["kind"] == "operation"


def test_maintained_ci_recipe_delegates_to_structured_report():
    recipe = Path("sampler/ci/__main__.rx").read_text(encoding="utf-8")
    assert recipe.strip().endswith("ci report")
