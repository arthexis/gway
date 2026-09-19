"""Discovery of Sous Chef jobs from Gway project manifests."""

from pathlib import Path

from .manifest import load


def declares_jobs(manifest):
    """Return whether a manifest declares a [sous-chef] job table."""
    try:
        lines = Path(manifest).read_text(encoding="utf-8").splitlines()
    except OSError:
        return False
    for raw in lines:
        line = raw.split("#", 1)[0].strip()
        if line == "[sous-chef]" or line.startswith("[sous-chef."):
            return True
    return False


def discover(runtime, installations=(), *, local_manifest=None):
    """Discover project-owned Sous Chef jobs without executing them."""
    jobs = {}

    for installation in installations:
        manifest = installation.install_path / "gway.toml"
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
            # The nearest local manifest is the active project view and wins
            # over a managed copy of that same project/job.
            jobs[job.identity] = job

    runtime._souschef_jobs = jobs
    return jobs
