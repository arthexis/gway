"""Generic external-process ingestion."""

from dataclasses import dataclass
from pathlib import Path
import os
import shutil
import subprocess

from ..identity import execution_identity
from .base import IngestedOperation, normalize_path, register_operation, remember_object


@dataclass(frozen=True)
class ProcessResult:
    """Structured result from one successfully completed external process."""

    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str


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
    executable = str(Path(executable).expanduser().resolve())

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
        completed = subprocess.run(
            command,
            check=True,
            text=True,
            capture_output=True,
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
        return path.resolve()

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
