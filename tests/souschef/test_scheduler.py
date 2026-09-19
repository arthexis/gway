import threading
import time

from gway.souschef import Job, Scheduler


def test_duplicate_pending_job_coalesces_reasons(tmp_path, job_factory):
    job = job_factory("cleanup")
    calls = []
    scheduler = Scheduler([job], executor=lambda current: calls.append(current.identity))

    assert scheduler.enqueue(job, "every") is True
    assert scheduler.enqueue(job, "watch") is False
    assert scheduler.enqueue(job, "every") is False

    assert scheduler.pending == (job,)

    result = scheduler.run_next()

    assert result.success is True
    assert result.reasons == ("every", "watch")
    assert calls == [("demo", "cleanup")]
    assert scheduler.pending == ()
    assert scheduler.active is None


def test_jobs_run_fifo_and_failures_do_not_stop_scheduler(tmp_path, job_factory):
    first = job_factory("first")
    second = job_factory("second")
    third = job_factory("third")
    calls = []

    def execute(job):
        calls.append(job.name)
        if job is second:
            raise RuntimeError("boom")
        return job.name.upper()

    scheduler = Scheduler([first, second, third], executor=execute)
    scheduler.enqueue(first, "manual")
    scheduler.enqueue(second, "manual")
    scheduler.enqueue(third, "manual")

    results = scheduler.drain()

    assert calls == ["first", "second", "third"]
    assert [result.success for result in results] == [True, False, True]
    assert results[0].value == "FIRST"
    assert isinstance(results[1].error, RuntimeError)
    assert str(results[1].error) == "boom"
    assert results[2].value == "THIRD"
    assert scheduler.active is None


def test_trigger_during_active_run_creates_one_follow_up(tmp_path, job_factory):
    job = job_factory("build")
    started = threading.Event()
    release = threading.Event()
    calls = []

    def execute(current):
        calls.append(current.identity)
        started.set()
        release.wait(timeout=5)

    scheduler = Scheduler([job], executor=execute)
    scheduler.enqueue(job, "every")

    worker = threading.Thread(target=scheduler.run_next)
    worker.start()
    assert started.wait(timeout=5)
    assert scheduler.active is job

    assert scheduler.enqueue(job, "watch") is True
    assert scheduler.enqueue(job, "down") is False
    assert scheduler.enqueue(job, "watch") is False
    assert scheduler.pending == (job,)

    release.set()
    worker.join(timeout=5)
    assert not worker.is_alive()

    follow_up = scheduler.run_next()

    assert follow_up.success is True
    assert follow_up.reasons == ("watch", "down")
    assert calls == [job.identity, job.identity]
    assert scheduler.pending == ()
    assert scheduler.active is None


def test_concurrent_run_next_calls_never_overlap(tmp_path, job_factory):
    first = job_factory("first")
    second = job_factory("second")
    state_lock = threading.Lock()
    active = 0
    maximum = 0
    order = []

    def execute(job):
        nonlocal active, maximum
        with state_lock:
            active += 1
            maximum = max(maximum, active)
            order.append(("start", job.name))
        time.sleep(0.05)
        with state_lock:
            order.append(("end", job.name))
            active -= 1

    scheduler = Scheduler([first, second], executor=execute)
    scheduler.enqueue(first)
    scheduler.enqueue(second)

    workers = [
        threading.Thread(target=scheduler.run_next),
        threading.Thread(target=scheduler.run_next),
    ]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join(timeout=5)
        assert not worker.is_alive()

    assert maximum == 1
    assert order == [
        ("start", "first"),
        ("end", "first"),
        ("start", "second"),
        ("end", "second"),
    ]
    assert scheduler.pending == ()
    assert scheduler.active is None


def test_same_job_name_is_distinct_across_projects(tmp_path, job_factory):
    alpha = job_factory("cleanup", project="alpha")
    beta = job_factory("cleanup", project="beta")
    scheduler = Scheduler(
        [alpha, beta],
        executor=lambda job: job.identity,
    )

    scheduler.enqueue(alpha, "watch")
    scheduler.enqueue(beta, "watch")

    results = scheduler.drain()

    assert [result.value for result in results] == [
        ("alpha", "cleanup"),
        ("beta", "cleanup"),
    ]


def test_scheduler_rejects_conflicting_identity(tmp_path, job_factory):
    original = job_factory("cleanup")
    conflicting = Job(
        project="demo",
        name="cleanup",
        root=tmp_path,
        recipe=tmp_path / "other.rx",
    )
    scheduler = Scheduler([original], executor=lambda job: None)

    try:
        scheduler.add([conflicting])
    except ValueError as exc:
        assert "Duplicate Sous Chef job identity" in str(exc)
    else:
        raise AssertionError("conflicting identity was accepted")
