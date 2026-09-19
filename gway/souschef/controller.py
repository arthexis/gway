"""Gateway-bound public Sous Chef operations."""

from .scheduler import Scheduler


class Controller:
    """Public Sous Chef job facade bound to one Gateway runtime."""

    def __init__(self, gateway):
        self.gateway = gateway

    def _job(self, job, project=None):
        jobs = getattr(self.gateway, "_souschef_jobs", {})
        if project is not None:
            try:
                return jobs[(project, job)]
            except KeyError as exc:
                raise LookupError(
                    f"Unknown Sous Chef job {project!r}/{job!r}"
                ) from exc

        matches = [
            current
            for current in jobs.values()
            if current.name == job
        ]
        if not matches:
            raise LookupError(f"Unknown Sous Chef job {job!r}")
        if len(matches) > 1:
            owners = ", ".join(sorted(current.project for current in matches))
            raise LookupError(
                f"Ambiguous Sous Chef job {job!r}; specify --project "
                f"({owners})"
            )
        return matches[0]

    def list(self, project=None):
        """List discovered Sous Chef jobs.

        Args:
            project: Optional owning project used to filter jobs.
        """
        jobs = getattr(self.gateway, "_souschef_jobs", {}).values()
        if project is not None:
            jobs = (
                job
                for job in jobs
                if job.project == project
            )
        return [
            {
                "project": job.project,
                "job": job.name,
                "recipe": str(job.recipe),
                "triggers": list(job.triggers),
                "timeout": job.timeout,
            }
            for job in sorted(jobs, key=lambda item: item.identity)
        ]

    def inspect(self, job, project=None):
        """Return one normalized Sous Chef job definition."""
        current = self._job(job, project)
        return {
            "project": current.project,
            "job": current.name,
            "recipe": str(current.recipe),
            "every": current.every,
            "watch": str(current.watch) if current.watch is not None else None,
            "down": current.down,
            "timeout": current.timeout,
            "triggers": list(current.triggers),
        }

    def run(self, job, project=None):
        """Run one Sous Chef job immediately through the single-worker scheduler."""
        current = self._job(job, project)
        scheduler = Scheduler([current])
        scheduler.enqueue(current, "manual")
        result = scheduler.run_next()
        return {
            "project": current.project,
            "job": current.name,
            "success": result.success,
            "reasons": list(result.reasons),
            "value": result.value,
            "error": str(result.error) if result.error is not None else None,
        }
