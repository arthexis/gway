"""Canonical structured CI result for the maintained Gway CI recipe."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

from gway.gateway import Gateway
from gway.outcome import ExitResult
from gway.recipe.validation import RecipeValidationError, validate_recipes


_CANONICAL_STATES = {
    0: "passed",
    1: "failed",
    2: "failed",
    3: "failed",
    4: "failed",
    5: "neutral",
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _failure_id(case):
    file_name = case.get("file")
    name = case.get("name") or "unknown"
    if file_name:
        return f"{file_name}::{name}"
    class_name = case.get("classname")
    return f"{class_name}::{name}" if class_name else name


def _parse_junit(path):
    root = ET.parse(path).getroot()
    suites = [root] if root.tag == "testsuite" else list(root.findall("testsuite"))

    totals = {"tests": 0, "failed": 0, "errors": 0, "skipped": 0, "duration": 0.0}
    failures = []

    for suite in suites:
        totals["tests"] += int(suite.get("tests", 0))
        totals["failed"] += int(suite.get("failures", 0))
        totals["errors"] += int(suite.get("errors", 0))
        totals["skipped"] += int(suite.get("skipped", 0))
        totals["duration"] += float(suite.get("time", 0.0))

        for case in suite.iter("testcase"):
            problem = case.find("failure")
            category = "assertion"
            if problem is None:
                problem = case.find("error")
                category = "error"
            if problem is None:
                continue
            problem_type = (problem.get("type") or "").casefold()
            if "timeout" in problem_type:
                category = "timeout"
            failures.append(
                {
                    "id": _failure_id(case),
                    "category": category,
                    "summary": problem.get("message")
                    or (problem.text or "").strip().split("\n", 1)[0],
                }
            )

    totals["passed"] = max(
        totals["tests"] - totals["failed"] - totals["errors"] - totals["skipped"],
        0,
    )
    totals["duration"] = round(totals["duration"], 3)
    totals["failures"] = failures
    return totals


def report(root="tests", workers: int = 4, durations: int = 20):
    """Run maintained project CI and return one canonical structured result.

    Ordinary CI failures are returned as structured data with a non-zero process
    exit status. Unexpected Gway implementation errors are deliberately not
    swallowed into the CI result contract.
    """
    started_at = _now()
    started = time.monotonic()

    try:
        validation = validate_recipes(Gateway(), "sampler")
    except RecipeValidationError as exc:
        completed_at = _now()
        return ExitResult(
            {
                "state": "failed",
                "phase": "validation",
                "suite": "integration",
                "started_at": started_at,
                "completed_at": completed_at,
                "duration": round(time.monotonic() - started, 3),
                "validation": {
                    "state": "failed",
                    "kind": "recipe",
                    "message": str(exc),
                },
                "tests": None,
            },
            exit_code=1,
        )

    with tempfile.TemporaryDirectory(prefix="gway-ci-") as directory:
        junit = Path(directory) / "pytest.xml"
        command = [
            sys.executable,
            "-m",
            "pytest",
            str(root),
            "--junitxml",
            str(junit),
        ]
        if durations is not None:
            command.extend(["--durations", str(durations)])
        if workers:
            command.extend(["-n", str(workers), "--dist", "loadgroup"])

        completed = subprocess.run(command, check=False)
        test_result = (
            _parse_junit(junit)
            if junit.is_file()
            else {
                "tests": None,
                "passed": None,
                "failed": None,
                "errors": None,
                "skipped": None,
                "duration": None,
                "failures": [],
            }
        )

    state = _CANONICAL_STATES.get(completed.returncode, "failed")
    test_result.update(
        {
            "state": state,
            "returncode": completed.returncode,
            "command": command,
        }
    )
    completed_at = _now()
    return ExitResult(
        {
            "state": state,
            "phase": "complete" if state in {"passed", "neutral"} else "tests",
            "suite": "integration",
            "started_at": started_at,
            "completed_at": completed_at,
            "duration": round(time.monotonic() - started, 3),
            "validation": {"state": "passed", **validation},
            "tests": test_result,
        },
        exit_code=0 if state in {"passed", "neutral"} else max(completed.returncode, 1),
    )
