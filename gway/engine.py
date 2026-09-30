"""Syntax validation for rendered engine configuration candidates."""

from pathlib import Path
import shutil
import subprocess
import tempfile

from .host import run_as_identity


class EngineValidationError(RuntimeError):
    """Raised when an engine rejects rendered candidate configuration."""


_DIAGNOSTIC_TOKEN = re.compile(r"[A-Za-z0-9_./@+=-]+")


def _diagnostic_excerpt(content, *, max_lines=8, max_line_chars=160, max_chars=800):
    """Return a bounded structural excerpt without resolved values."""
    rendered = []
    for index, raw in enumerate(str(content).splitlines()[:max_lines], start=1):
        line = raw[:max_line_chars]
        shaped = _DIAGNOSTIC_TOKEN.sub("<text>", line)
        if len(raw) > max_line_chars:
            shaped += "…"
        rendered.append(f"{index:>3}: {shaped}")
    return "\n".join(rendered)[:max_chars]


def _nginx(content, *, executable=None, identity=None):
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
        argv = [executable, "-t", "-c", str(config), "-p", str(root)]
        if identity is None:
            completed = subprocess.run(
                argv,
                check=False,
                capture_output=True,
                text=True,
            )
        else:
            completed = run_as_identity(
                identity,
                *argv,
                check=False,
                capture_output=True,
                text=True,
            )
    if completed.returncode:
        detail = completed.stderr.strip() or completed.stdout.strip()
        excerpt = _diagnostic_excerpt(content)
        raise EngineValidationError(
            "nginx rejected rendered configuration: "
            f"{detail}\nrendered candidate shape:\n{excerpt}"
        )


_VALIDATORS = {
    "nginx": _nginx,
}


def validate_text(engine, content, *, executable=None, identity=None):
    """Validate fully rendered text with a named engine before mutation."""
    name = str(engine).strip().lower()
    try:
        validator = _VALIDATORS[name]
    except KeyError as error:
        supported = ", ".join(sorted(_VALIDATORS))
        raise ValueError(
            f"Unknown render validation engine {engine!r}; supported: {supported}"
        ) from error
    validator(str(content), executable=executable, identity=identity)
    return content
