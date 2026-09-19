from gway.souschef import Job, Scheduler, StateStore, TriggerEngine


class Clock:
    def __init__(self, value=1000.0):
        self.value = value

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def make_job(tmp_path, name, **kwargs):
    return Job(
        project="demo",
        name=name,
        root=tmp_path,
        recipe=tmp_path / f"{name}.rx",
        **kwargs,
    )


def test_every_is_immediately_due_then_waits_for_interval(tmp_path):
    clock = Clock()
    job = make_job(tmp_path, "hourly", every=3600)
    scheduler = Scheduler([job], executor=lambda current: current.name)
    engine = TriggerEngine(
        [job],
        scheduler=scheduler,
        state_root=tmp_path / "state",
        clock=clock,
    )

    assert engine.evaluate_job(job) == ("every",)
    result = scheduler.run_next()
    assert result.success is True

    assert engine.evaluate_job(job) == ()

    clock.advance(3599)
    assert engine.evaluate_job(job) == ()

    clock.advance(1)
    assert engine.evaluate_job(job) == ("every",)


def test_every_state_survives_engine_restart(tmp_path):
    clock = Clock()
    job = make_job(tmp_path, "hourly", every=60)
    state_root = tmp_path / "state"
    scheduler = Scheduler([job], executor=lambda current: None)
    engine = TriggerEngine(
        [job],
        scheduler=scheduler,
        state_root=state_root,
        clock=clock,
    )
    engine.evaluate_job(job)
    scheduler.run_next()

    clock.advance(30)
    restarted = TriggerEngine(
        [job],
        scheduler=Scheduler([job], executor=lambda current: None),
        state_root=state_root,
        clock=clock,
    )

    assert restarted.evaluate_job(job) == ()


def test_watch_baselines_then_fires_on_change(tmp_path):
    watched = tmp_path / "settings.toml"
    watched.write_text("one", encoding="utf-8")
    job = make_job(tmp_path, "watcher", watch=watched)
    scheduler = Scheduler([job], executor=lambda current: None)
    engine = TriggerEngine(
        [job],
        scheduler=scheduler,
        state_root=tmp_path / "state",
    )

    assert engine.evaluate_job(job) == ()
    assert scheduler.pending == ()

    watched.write_text("two", encoding="utf-8")
    assert engine.evaluate_job(job) == ("watch",)
    assert scheduler.pending == (job,)

    assert engine.evaluate_job(job) == ()


def test_watch_state_survives_restart(tmp_path):
    watched = tmp_path / "settings.toml"
    watched.write_text("one", encoding="utf-8")
    job = make_job(tmp_path, "watcher", watch=watched)
    state_root = tmp_path / "state"

    first = TriggerEngine(
        [job],
        scheduler=Scheduler([job], executor=lambda current: None),
        state_root=state_root,
    )
    assert first.evaluate_job(job) == ()

    restarted = TriggerEngine(
        [job],
        scheduler=Scheduler([job], executor=lambda current: None),
        state_root=state_root,
    )
    assert restarted.evaluate_job(job) == ()

    watched.write_text("two", encoding="utf-8")
    assert restarted.evaluate_job(job) == ("watch",)


def test_down_fires_once_per_down_transition(tmp_path):
    running = {"value": True}

    def status(project, service):
        assert (project, service) == ("arthexis", "web-local")
        return {"running": running["value"]}

    job = make_job(
        tmp_path,
        "recover",
        down="arthexis/web-local",
    )
    scheduler = Scheduler([job], executor=lambda current: None)
    engine = TriggerEngine(
        [job],
        scheduler=scheduler,
        state_root=tmp_path / "state",
        service_status=status,
    )

    assert engine.evaluate_job(job) == ()

    running["value"] = False
    assert engine.evaluate_job(job) == ("down",)
    assert engine.evaluate_job(job) == ()

    running["value"] = True
    assert engine.evaluate_job(job) == ()

    running["value"] = False
    assert engine.evaluate_job(job) == ("down",)


def test_missing_service_counts_as_down(tmp_path):
    def missing(project, service):
        raise LookupError("missing")

    job = make_job(tmp_path, "recover", down="demo/missing")
    scheduler = Scheduler([job], executor=lambda current: None)
    engine = TriggerEngine(
        [job],
        scheduler=scheduler,
        state_root=tmp_path / "state",
        service_status=missing,
    )

    assert engine.evaluate_job(job) == ("down",)


def test_future_url_down_target_is_not_interpreted_as_service(tmp_path):
    calls = []

    def status(project, service):
        calls.append((project, service))
        return {"running": False}

    job = make_job(
        tmp_path,
        "website",
        down="https://example.com/health",
    )
    engine = TriggerEngine(
        [job],
        scheduler=Scheduler([job], executor=lambda current: None),
        state_root=tmp_path / "state",
        service_status=status,
    )

    assert engine.evaluate_job(job) == ()
    assert calls == []


def test_simultaneous_triggers_coalesce_into_one_pending_run(tmp_path):
    clock = Clock()
    watched = tmp_path / "watched.txt"
    watched.write_text("one", encoding="utf-8")
    running = {"value": True}
    job = make_job(
        tmp_path,
        "combined",
        every=60,
        watch=watched,
        down="demo/service",
    )
    scheduler = Scheduler([job], executor=lambda current: None)
    engine = TriggerEngine(
        [job],
        scheduler=scheduler,
        state_root=tmp_path / "state",
        service_status=lambda project, service: {"running": running["value"]},
        clock=clock,
    )

    # First evaluation establishes watch/down baselines and queues the initial
    # interval run.
    assert engine.evaluate_job(job) == ("every",)
    scheduler.run_next()

    clock.advance(60)
    watched.write_text("two", encoding="utf-8")
    running["value"] = False

    reasons = engine.evaluate_job(job)

    assert reasons == ("every", "watch", "down")
    assert scheduler.pending == (job,)
    result = scheduler.run_next()
    assert result.reasons == ("every", "watch", "down")


def test_pending_job_is_restored_after_restart(tmp_path):
    job = make_job(tmp_path, "hourly", every=60)
    state_root = tmp_path / "state"
    first_scheduler = Scheduler([job], executor=lambda current: None)
    first = TriggerEngine(
        [job],
        scheduler=first_scheduler,
        state_root=state_root,
    )

    assert first.evaluate_job(job) == ("every",)
    assert StateStore(state_root).get(*job.identity).pending is True

    second_scheduler = Scheduler([job], executor=lambda current: None)
    second = TriggerEngine(
        [job],
        scheduler=second_scheduler,
        state_root=state_root,
    )

    assert second_scheduler.pending == (job,)
    result = second_scheduler.run_next()
    assert result.reasons == ("resume",)
    assert StateStore(state_root).get(*job.identity).pending is False


def test_run_state_records_success_and_failure(tmp_path):
    clock = Clock()
    success = make_job(tmp_path, "success", every=60)
    failure = make_job(tmp_path, "failure", every=60)

    def execute(job):
        if job is failure:
            raise RuntimeError("boom")
        return "ok"

    scheduler = Scheduler([success, failure], executor=execute)
    state_root = tmp_path / "state"
    engine = TriggerEngine(
        [success, failure],
        scheduler=scheduler,
        state_root=state_root,
        clock=clock,
    )

    engine.evaluate()
    first, second = scheduler.drain()

    success_state = StateStore(state_root).get(*success.identity)
    failure_state = StateStore(state_root).get(*failure.identity)

    assert first.success is True
    assert second.success is False
    assert success_state.last_started == 1000.0
    assert success_state.last_completed == 1000.0
    assert success_state.last_success == 1000.0
    assert success_state.last_failure is None
    assert failure_state.last_started == 1000.0
    assert failure_state.last_completed == 1000.0
    assert failure_state.last_failure == 1000.0
    assert failure_state.last_success is None
