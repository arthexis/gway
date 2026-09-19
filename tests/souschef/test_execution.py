import time

from gway.souschef import (
    Job,
    RecipeExecutionError,
    RecipeExecutor,
    RecipeTimeoutError,
    Scheduler,
)


def write_recipe(root, name, body, recipe_line):
    recipe = root / f"{name}.rx"
    companion = root / f"{name}.py"
    companion.write_text(body, encoding="utf-8")
    recipe.write_text(recipe_line + "\n", encoding="utf-8")
    return recipe


def make_job(root, name, *, timeout=5):
    return Job(
        project="demo",
        name=name,
        root=root,
        recipe=root / f"{name}.rx",
        timeout=timeout,
    )


def test_recipe_executor_uses_canonical_recipe_evaluator(tmp_path):
    output = tmp_path / "done.txt"
    write_recipe(
        tmp_path,
        "success",
        "from pathlib import Path\n"
        f"def mark():\n    Path({str(output)!r}).write_text('done', encoding='utf-8')\n"
        "    return 'ok'\n",
        "mark",
    )
    job = make_job(tmp_path, "success")
    executor = RecipeExecutor()

    value = executor(job)

    assert value == "ok"
    assert output.read_text(encoding="utf-8") == "done"


def test_recipe_failure_does_not_stop_later_scheduler_work(tmp_path):
    write_recipe(
        tmp_path,
        "fail",
        "def explode():\n    raise RuntimeError('boom')\n",
        "explode",
    )
    output = tmp_path / "after.txt"
    write_recipe(
        tmp_path,
        "after",
        "from pathlib import Path\n"
        f"def mark():\n    Path({str(output)!r}).write_text('after', encoding='utf-8')\n"
        "    return 'after'\n",
        "mark",
    )
    failed = make_job(tmp_path, "fail")
    after = make_job(tmp_path, "after")
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


def test_timed_out_recipe_is_terminated_and_scheduler_continues(tmp_path):
    write_recipe(
        tmp_path,
        "slow",
        "import time\n"
        "def wait():\n    time.sleep(30)\n",
        "wait",
    )
    output = tmp_path / "after-timeout.txt"
    write_recipe(
        tmp_path,
        "after",
        "from pathlib import Path\n"
        f"def mark():\n    Path({str(output)!r}).write_text('ok', encoding='utf-8')\n"
        "    return 'ok'\n",
        "mark",
    )
    slow = make_job(tmp_path, "slow", timeout=0.2)
    after = make_job(tmp_path, "after", timeout=5)
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
