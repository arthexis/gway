"""Syntax validation for rendered engine configuration candidates."""

from pathlib import Path
import shutil
import subprocess
import tempfile


class EngineValidationError(RuntimeError):
    """Raised when an engine rejects rendered candidate configuration."""


def _nginx(content, *, executable=None):
    executable = str(executable or shutil.which("nginx") or "nginx")
    with tempfile.TemporaryDirectory(prefix="gway-nginx-check-") as directory:
        root = Path(directory)
        candidate = root / "candidate.conf"
        candidate.write_text(content, encoding="utf-8")
        config = root / "nginx.conf"
        config.write_text(
            "\n".join(
                (
                    "worker_processes 1;",
                    f"error_log {root / 'error.log'};",
                    f"pid {root / 'nginx.pid'};",
                    "events { worker_connections 16; }",
                    "http {",
                    f"    include {candidate};",
                    "}",
                    "",
                )
            ),
            encoding="utf-8",
        )
        completed = subprocess.run(
            [executable, "-t", "-c", str(config), "-p", str(root)],
            check=False,
            capture_output=True,
            text=True,
        )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise EngineValidationError(f"nginx rejected rendered configuration: {detail}")


_VALIDATORS = {
    "nginx": _nginx,
}


def validate_text(engine, content, *, executable=None):
    """Validate fully rendered text with a named engine before mutation."""
    name = str(engine).strip().lower()
    try:
        validator = _VALIDATORS[name]
    except KeyError as error:
        supported = ", ".join(sorted(_VALIDATORS))
        raise ValueError(
            f"Unknown render validation engine {engine!r}; supported: {supported}"
        ) from error
    validator(str(content), executable=executable)
    return content
