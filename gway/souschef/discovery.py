"""Discovery of Sous Chef jobs from standard project metadata."""

from .project_file import load


def declares_jobs(project_file):
    """Return whether pyproject declares [tool.gway.sous-chef] jobs."""
    try:
        from .. import toml
        data = toml.load(project_file)
    except (OSError, ValueError):
        return False

    tool = data.get("tool") if isinstance(data, dict) else None
    gway = tool.get("gway") if isinstance(tool, dict) else None
    jobs = gway.get("sous-chef") if isinstance(gway, dict) else None
    return isinstance(jobs, dict) and bool(jobs)


def discover(runtime, installations=(), *, local_project_file=None):
    """Discover project-owned Sous Chef jobs without executing them."""
    jobs = {}

    for installation in installations:
        project_file = installation.install_path / "pyproject.toml"
        if not declares_jobs(project_file):
            continue
        for job in load(project_file):
            existing = jobs.get(job.identity)
            if existing is not None and existing != job:
                raise RuntimeError(
                    f"Duplicate Sous Chef job identity: {job.identity!r}"
                )
            jobs[job.identity] = job

    if local_project_file is not None and declares_jobs(local_project_file):
        for job in load(local_project_file):
            jobs[job.identity] = job

    runtime._souschef_jobs = jobs
    return jobs
