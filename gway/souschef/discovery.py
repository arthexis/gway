"""Discovery of Sous Chef jobs from standard project metadata."""

from pathlib import Path

from .manifest import load


def declares_jobs(manifest):
    """Return whether pyproject declares [tool.gway.sous-chef] jobs."""
    try:
        from .. import toml
        data = toml.load(manifest)
    except (OSError, ValueError):
        return False

    tool = data.get("tool") if isinstance(data, dict) else None
    gway = tool.get("gway") if isinstance(tool, dict) else None
    jobs = gway.get("sous-chef") if isinstance(gway, dict) else None
    return isinstance(jobs, dict) and bool(jobs)


def discover(runtime, installations=(), *, local_manifest=None):
    """Discover project-owned Sous Chef jobs without executing them."""
    jobs = {}

    for installation in installations:
        manifest = installation.install_path / "pyproject.toml"
        if not declares_jobs(manifest):
            continue
        for job in load(manifest):
            existing = jobs.get(job.identity)
            if existing is not None and existing != job:
                raise RuntimeError(
                    f"Duplicate Sous Chef job identity: {job.identity!r}"
                )
            jobs[job.identity] = job

    if local_manifest is not None and declares_jobs(local_manifest):
        for job in load(local_manifest):
            jobs[job.identity] = job

    runtime._souschef_jobs = jobs
    return jobs
