import time

from gway.souschef import (
    RecipeExecutionError,
    RecipeExecutor,
    RecipeTimeoutError,
    Scheduler,
)


def test_recipe_executor_uses_canonical_recipe_evaluator(
    tmp_path, job_factory, recipe_factory
):
    output = tmp_path / "done.txt"
    recipe_factory(
        tmp_path,
        "success",
        "from pathlib import Path\n"
        f"def mark():\n    Path({str(output)!r}).write_text('done', encoding='utf-8')\n"
        "    return 'ok'\n",
        "success mark",
    )
    job = job_factory("success", timeout=5)
    executor = RecipeExecutor()

    value = executor(job)

    assert value == "ok"
    assert output.read_text(encoding="utf-8") == "done"


def test_recipe_failure_does_not_stop_later_scheduler_work(
    tmp_path, job_factory, recipe_factory
):
    recipe_factory(
        tmp_path,
        "fail",
        "def explode():\n    raise RuntimeError('boom')\n",
        "fail explode",
    )
    output = tmp_path / "after.txt"
    recipe_factory(
        tmp_path,
        "after",
        "from pathlib import Path\n"
        f"def mark():\n    Path({str(output)!r}).write_text('after', encoding='utf-8')\n"
        "    return 'after'\n",
        "after mark",
    )
    failed = job_factory("fail", timeout=5)
    after = job_factory("after", timeout=5)
    scheduler = Scheduler([failed, after])
    scheduler.enqueue(failed)
    scheduler.enqueue(after)

    results = scheduler.drain()

    assert len(results) == 2
    assert results[0].success is False
    assert isinstance(results[0].error, RecipeExecutionError)
    assert "RuntimeError: boom" in str(results[0].error)
    assert results[1].success is True
    assert results[1].value == "after"
    assert output.read_text(encoding="utf-8") == "after"


def test_timed_out_recipe_is_terminated_and_scheduler_continues(
    tmp_path, job_factory, recipe_factory
):
    recipe_factory(
        tmp_path,
        "slow",
        "import time\ndef wait():\n    time.sleep(30)\n",
        "slow wait",
    )
    output = tmp_path / "after-timeout.txt"
    recipe_factory(
        tmp_path,
        "after",
        "from pathlib import Path\n"
        f"def mark():\n    Path({str(output)!r}).write_text('ok', encoding='utf-8')\n"
        "    return 'ok'\n",
        "after mark",
    )
    slow = job_factory("slow", timeout=0.2)
    after = job_factory("after", timeout=5)
    scheduler = Scheduler([slow, after])
    scheduler.enqueue(slow)
    scheduler.enqueue(after)

    started = time.monotonic()
    results = scheduler.drain()
    elapsed = time.monotonic() - started

    assert len(results) == 2
    assert results[0].success is False
    assert isinstance(results[0].error, RecipeTimeoutError)
    assert "0.2s timeout" in str(results[0].error)
    assert results[1].success is True
    assert results[1].value == "ok"
    assert output.read_text(encoding="utf-8") == "ok"
    assert elapsed < 10
