"""Shared host command execution under a semantic execution identity."""

import subprocess


def run_as_identity(identity, *argv, check=True, **kwargs):
    """Run one host command using an ExecutionIdentity."""
    return subprocess.run(
        identity.command(*argv),
        check=check,
        **kwargs,
    )
