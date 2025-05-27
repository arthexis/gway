import time
import asyncio
import threading
from datetime import datetime, timedelta


# Internal storage for scheduled jobs
_jobs = []
_scheduler_thread = None
_stop_event = threading.Event()


class _ScheduledJob:
    def __init__(self, recipe: str, *, cron: str = None, delay: float = None, repeat: bool = False):
        self.recipe = recipe
        self.cron = cron
        self.delay = delay
        self.repeat = repeat
        self.next_run = self._compute_next_run()

    def _compute_next_run(self) -> datetime:
        from croniter import croniter
        now = datetime.now()
        if self.cron:
            base = now
            iter = croniter(self.cron, base)
            return iter.get_next(datetime)
        elif self.delay is not None:
            return now + timedelta(seconds=self.delay)
        else:
            raise ValueError("Either cron or delay must be specified")

    def update_next(self):
        if self.repeat:
            self.next_run = self._compute_next_run()
        else:
            _jobs.remove(self)


def _scheduler_loop(threaded: bool):
    from gway import gw, Gateway
    while not _stop_event.is_set():
        now = datetime.now()
        for job in list(_jobs):
            if job.next_run <= now:
                def _run(job):
                    gw.info(f"[Scheduler] Executing recipe: {job.recipe}")
                    gw.run_recipe(job.recipe)

                if threaded:
                    threading.Thread(target=_run, args=(job,), daemon=True).start()
                else:
                    _run(job)

                job.update_next()

        time.sleep(1)


def schedule(recipe: str, *, 
             cron: str = None, delay: float = None, repeat: bool = False, 
             daemon: bool = False, threaded: bool = True):
    """
    Schedule a recipe to run.

    :param recipe: Path to the batch recipe file
    :param cron: A cron expression (e.g. '0 2 * * *') for scheduled time
    :param delay: Delay in seconds before first run
    :param repeat: Whether to repeat according to cron/delay
    :param daemon: Run scheduler loop in daemon thread or return an awaitable
    :param threaded: Execute each job in its own thread
    :return: Coroutine if daemon=True, otherwise the ScheduledJob instance
    """
    job = _ScheduledJob(recipe, cron=cron, delay=delay, repeat=repeat)
    _jobs.append(job)

    global _scheduler_thread
    if _scheduler_thread is None:
        def start_loop():
            _scheduler_loop(threaded)
        
        if daemon:
            return asyncio.to_thread(start_loop)
        else:
            _scheduler_thread = threading.Thread(target=start_loop, daemon=True)
            _scheduler_thread.start()

    return job
