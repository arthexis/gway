"""Generic external-process ingestion."""

from dataclasses import dataclass
from pathlib import Path
import os
import re
import shlex
import shutil
import subprocess
import time
from urllib.parse import urlsplit, urlunsplit

from ..identity import execution_identity
from .. import log
from .base import IngestedOperation, normalize_path, register_operation, remember_object


@dataclass(frozen=True)
class ProcessResult:
    """Structured result from one successfully completed external process."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


_DIAGNOSTIC_LIMIT = 4000
_SENSITIVE_OPTION_RE = re.compile(
    r"(?:authorization|cookie|credential|password|passwd|secret|token|api[-_]?key|"
    r"private[-_]?key|signature)",
    re.I,
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(authorization|cookie|credential|password|passwd|secret|token|"
    r"api[-_]?key|private[-_]?key|signature)\s*[:=]\s*([^\s&]+)"
)


def _bounded(value, *, limit=_DIAGNOSTIC_LIMIT):
    text = "" if value is None else str(value)
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[-limit:] + "...<truncated>"


def _safe_url(value):
    try:
        parsed = urlsplit(str(value))
    except ValueError:
        return str(value)
    if not parsed.scheme or not parsed.netloc:
        return str(value)
    host = parsed.hostname or ""
    if parsed.port is not None:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


def _redact_text(value):
    text = _bounded(value)
    if not text:
        return ""
    text = _SENSITIVE_ASSIGNMENT_RE.sub(lambda m: f"{m.group(1)}=<redacted>", text)
    return text


def _safe_command(command):
    safe = []
    redact_next = False
    for raw in command:
        value = str(raw)
        if redact_next:
            safe.append("<redacted>")
            redact_next = False
            continue
        if value.startswith("--"):
            name, sep, assigned = value.partition("=")
            if _SENSITIVE_OPTION_RE.search(name):
                if sep:
                    safe.append(f"{name}=<redacted>")
                else:
                    safe.append(name)
                    redact_next = True
                continue
        safe.append(_safe_url(value))
    return tuple(safe)


def _log_process(event, command, *, tool, returncode=None, stdout="", stderr="", elapsed=None):
    fields = [
        "[proc]",
        f"event={event}",
        f"tool={tool}",
        f"argv={shlex.join(_safe_command(command))}",
    ]
    if returncode is not None:
        fields.append(f"returncode={returncode}")
    if elapsed is not None:
        fields.append(f"elapsed={elapsed:.6f}s")
    safe_stdout = _redact_text(stdout)
    safe_stderr = _redact_text(stderr)
    if safe_stdout:
        fields.append(f"stdout={safe_stdout!r}")
    if safe_stderr:
        fields.append(f"stderr={safe_stderr!r}")
    message = " ".join(fields)
    if event == "failure":
        log.error(message)
    else:
        log.info(message)


def _option_argv(options):
    argv = []
    for name, value in options.items():
        option = "--" + name.replace("_", "-")
        if value is True:
            argv.append(option)
        elif value in (False, None):
            continue
        elif isinstance(value, (tuple, list)):
            for item in value:
                argv.extend((option, str(item)))
        else:
            argv.extend((option, str(value)))
    return argv


def _callable(executable, *, as_user=None):
    executable = os.path.abspath(os.fspath(Path(executable).expanduser()))

    def invoke(*arguments, sudo=False, **options):
        identity = execution_identity(
            as_user=as_user,
            sudo=sudo,
            options={"as": options.pop("as", None)} if "as" in options else None,
        )
        argv = [
            executable,
            *(str(argument) for argument in arguments),
            *_option_argv(options),
        ]
        command = identity.command(*argv)
        tool = Path(executable).name
        started = time.perf_counter()
        _log_process("start", command, tool=tool)
        try:
            completed = subprocess.run(
                command,
                check=True,
                text=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            _log_process(
                "failure",
                command,
                tool=tool,
                returncode=exc.returncode,
                stdout=exc.stdout,
                stderr=exc.stderr,
                elapsed=time.perf_counter() - started,
            )
            raise
        _log_process(
            "success",
            command,
            tool=tool,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            elapsed=time.perf_counter() - started,
        )
        return ProcessResult(
            argv=tuple(command),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    invoke.__name__ = Path(executable).name
    invoke.__doc__ = f"Run external process {executable!r}."
    return invoke


def _resolve_executable(source):
    source = str(source)
    if "/" in source or "\\" in source:
        path = Path(source).expanduser()
        if not path.is_file():
            raise FileNotFoundError(path)
        if not os.access(path, os.X_OK):
            raise ValueError(f"Process path is not executable: {path}")
        return Path(os.path.abspath(os.fspath(path)))

    found = shutil.which(source)
    if found is None:
        raise FileNotFoundError(f"Executable not found on PATH: {source}")
    return Path(found).resolve()


def ingest_proc(gateway, executable, *, path=None, sudo=False, **kwargs):
    """Ingest one executable as an argv-preserving Gway operation."""
    requested = Path(str(executable)).name
    resolved = _resolve_executable(executable)
    root = normalize_path(path or (requested,))
    callable_ = _callable(resolved, as_user="root" if sudo else None)
    record = remember_object(gateway, callable_, root)
    if record.registered:
        return []

    operation = IngestedOperation(
        root,
        callable_,
        source=resolved,
        kind="proc",
        metadata={"executable": str(resolved)},
    )
    wrapped = register_operation(gateway, operation)
    record.operation = wrapped
    record.operations[root] = wrapped
    record.registered = True
    record.expanded = True
    return [wrapped]


def ingest_path(gateway, path, **kwargs):
    """Ingest an executable from a filesystem path."""
    return ingest_proc(gateway, Path(path), **kwargs)
