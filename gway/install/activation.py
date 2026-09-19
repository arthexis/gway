"""Transactional activation of project-declared command launchers."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import uuid

from .model import validate_name
from ..project import scripts


_TARGET = re.compile(
    r"^(?P<module>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*):"
    r"(?P<attribute>[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)$"
)
_MARKER = "# gway-managed-launcher:"


def _index_path(paths, project):
    return paths.launchers / f"{project}.json"


def _read_index(paths, project):
    path = _index_path(paths, project)
    if not path.is_file():
        return {}
    value = json.loads(path.read_text(encoding="utf-8"))
    entries = value.get("scripts", {}) if isinstance(value, dict) else {}
    return entries if isinstance(entries, dict) else {}


def _write_index(paths, project, entries):
    paths.launchers.mkdir(parents=True, exist_ok=True)
    path = _index_path(paths, project)
    if not entries:
        if path.exists():
            path.unlink()
        return

    payload = {
        "project": project,
        "scripts": entries,
    }
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=paths.launchers,
        prefix=f".{project}.",
        suffix=".json",
        delete=False,
    ) as stream:
        json.dump(payload, stream, indent=2, sort_keys=True)
        stream.write("\n")
        temporary = Path(stream.name)
    os.replace(temporary, path)


def _launcher_text(project, command, target, project_path):
    module, attribute = target.split(":", 1)
    return (
        f"#!{sys.executable}\n"
        f"{_MARKER} {project} {command}\n"
        "import importlib\n"
        "import sys\n"
        f"sys.path.insert(0, {str(Path(project_path))!r})\n"
        f"_value = importlib.import_module({module!r})\n"
        f"for _part in {attribute.split('.')!r}:\n"
        "    _value = getattr(_value, _part)\n"
        "raise SystemExit(_value())\n"
    )


def _owned_launcher(path, project, command):
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            first = stream.readline()
            second = stream.readline().strip()
    except (OSError, UnicodeError):
        return False
    return second == f"{_MARKER} {project} {command}"


def _current_executable(path, command, project):
    if command != project:
        return False
    try:
        invoked = Path(sys.argv[0]).expanduser().resolve()
        return invoked == Path(path).resolve()
    except (OSError, RuntimeError):
        return False


@dataclass
class Activation:
    """Rollback/commit handle for launcher filesystem changes."""

    project: str
    paths: object
    previous: dict
    backups: list
    created: list
    active: bool = True

    def rollback(self):
        if not self.active:
            return
        for path in reversed(self.created):
            path = Path(path)
            if path.exists() or path.is_symlink():
                path.unlink()
        for original, backup in reversed(self.backups):
            original = Path(original)
            backup = Path(backup)
            if original.exists() or original.is_symlink():
                original.unlink()
            if backup.exists() or backup.is_symlink():
                os.replace(backup, original)
        _write_index(self.paths, self.project, self.previous)
        self.active = False

    def commit(self):
        if not self.active:
            return
        for _, backup in self.backups:
            backup = Path(backup)
            if backup.exists() or backup.is_symlink():
                try:
                    backup.unlink()
                except OSError:
                    pass
        self.active = False


def activate(project, project_path, paths):
    """Converge declared launchers and return a rollback/commit handle."""
    validate_name(project)
    desired = scripts(project_path)
    previous = _read_index(paths, project)

    if not desired and not previous:
        return Activation(project, paths, previous, [], [], active=False)

    paths.bin.mkdir(parents=True, exist_ok=True)
    backups = []
    created = []
    token = Activation(project, paths, previous, backups, created)

    try:
        all_commands = sorted(set(previous) | set(desired))
        for command in all_commands:
            validate_name(command)
            final = paths.bin / command
            old_owned = command in previous

            if command not in desired:
                if final.exists() or final.is_symlink():
                    if not _owned_launcher(final, project, command):
                        raise RuntimeError(
                            f"Refusing to remove unmanaged launcher: {final}"
                        )
                    backup = paths.bin / (
                        f".{command}.gway-backup-{uuid.uuid4().hex}"
                    )
                    os.replace(final, backup)
                    backups.append((final, backup))
                continue

            target = desired[command]
            text = _launcher_text(project, command, target, project_path)

            if final.is_file():
                try:
                    if final.read_text(encoding="utf-8") == text:
                        continue
                except UnicodeError:
                    pass

            if final.exists() or final.is_symlink():
                allowed = (
                    old_owned
                    and _owned_launcher(final, project, command)
                ) or _current_executable(final, command, project)
                if not allowed:
                    raise RuntimeError(
                        f"Refusing to replace unmanaged launcher: {final}"
                    )
                backup = paths.bin / (
                    f".{command}.gway-backup-{uuid.uuid4().hex}"
                )
                os.replace(final, backup)
                backups.append((final, backup))

            fd, temporary_name = tempfile.mkstemp(
                prefix=f".{command}.gway-",
                dir=paths.bin,
            )
            os.close(fd)
            temporary = Path(temporary_name)
            try:
                temporary.write_text(text, encoding="utf-8")
                temporary.chmod(0o755)
                os.replace(temporary, final)
            finally:
                if temporary.exists():
                    temporary.unlink()
            created.append(final)

        _write_index(paths, project, desired)
        return token
    except Exception:
        token.rollback()
        raise


def deactivate(project, paths):
    """Temporarily deactivate owned launchers for transactional uninstall."""
    validate_name(project)
    previous = _read_index(paths, project)
    backups = []
    token = Activation(project, paths, previous, backups, [])

    try:
        for command in sorted(previous):
            final = paths.bin / command
            if not final.exists() and not final.is_symlink():
                continue
            if not _owned_launcher(final, project, command):
                raise RuntimeError(
                    f"Refusing to remove unmanaged launcher: {final}"
                )
            backup = paths.bin / (
                f".{command}.gway-backup-{uuid.uuid4().hex}"
            )
            os.replace(final, backup)
            backups.append((final, backup))

        _write_index(paths, project, {})
        return token
    except Exception:
        token.rollback()
        raise
