"""Setuptools bridge for recursively installed sampler data."""

from pathlib import Path

from setuptools import setup


ROOT = Path(__file__).parent
SAMPLER = ROOT / "sampler"


def sampler_data_files():
    """Preserve the complete sampler tree under share/gway/sampler."""
    grouped = []
    for directory in sorted(path for path in SAMPLER.rglob("*") if path.is_dir()):
        files = sorted(path for path in directory.iterdir() if path.is_file())
        if not files:
            continue
        relative = directory.relative_to(SAMPLER)
        destination = Path("share") / "gway" / "sampler" / relative
        grouped.append(
            (str(destination), [str(path.relative_to(ROOT)) for path in files])
        )
    return grouped


setup(data_files=sampler_data_files())
