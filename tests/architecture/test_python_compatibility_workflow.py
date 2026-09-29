from pathlib import Path


def test_python_compatibility_workflow_propagates_failures_and_runs_on_main_push():
    workflow = Path(".github/workflows/python-compatibility.yml").read_text(
        encoding="utf-8"
    )

    assert "push:" in workflow
    assert "branches: [main]" in workflow
    assert "python -m gway test run architecture - check --is 0" in workflow
    assert (
        'python -m gway test run --keyword "not architecture" - check --is 0'
        in workflow
    )
