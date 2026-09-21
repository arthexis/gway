"""Generic sigil-aware filesystem operations."""

import os
from pathlib import Path
import shutil

from .host import run_as_identity
from .identity import execution_identity


def _path(runtime, value):
    return Path(str(runtime.resolve(str(value)))).expanduser()


def _destination(source, destination):
    if destination.is_dir():
        return destination / source.name
    return destination


def _identity(*, sudo=False, options=None):
    return execution_identity(sudo=sudo, options=options)


def _copy_local(source, destination):
    target = _destination(source, destination)
    if source.is_dir():
        return Path(shutil.copytree(source, target))
    return Path(shutil.copy2(source, target))


def _move_local(source, destination):
    target = _destination(source, destination)
    return Path(shutil.move(str(source), str(target)))


def _link_local(source, destination):
    target = _destination(source, destination)
    if target.is_symlink() and target.resolve() == source.resolve():
        return target
    os.symlink(source, target, target_is_directory=source.is_dir())
    return target


def _remove_local(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        path.rmdir()
    else:
        raise FileNotFoundError(path)
    return path


class Filesystem:
    """Runtime-bound generic filesystem operations."""

    def __init__(self, runtime):
        self.runtime = runtime

    def copy(self, source, to, sudo=False, rollback=None, **options):
        """Copy a file or directory to another path."""
        source = _path(self.runtime, source)
        destination = _path(self.runtime, to)
        identity = _identity(sudo=sudo, options=options)
        target = _destination(source, destination)

        entry = None
        if rollback is None:
            self.runtime.debug("rollback-capable copy executed without journal")
        else:
            self.runtime.debug(
                "transaction mutation journal=%s operation=copy path=%s",
                rollback,
                target,
            )
            entry = self.runtime.journal.prepare_path(
                rollback,
                operation="copy",
                path=target,
                identity=identity,
            )

        if entry is not None:
            self.runtime.journal.mark_mutated(rollback, entry.sequence)

        if not identity.privileged:
            result = _copy_local(source, destination)
        else:
            run_as_identity(identity, "cp", "-a", source, target)
            result = target

        if entry is not None:
            self.runtime.journal.mark_applied(rollback, entry.sequence)
        return result

    def move(self, source, to, sudo=False, rollback=None, **options):
        """Move a file or directory to another path."""
        source = _path(self.runtime, source)
        destination = _path(self.runtime, to)
        identity = _identity(sudo=sudo, options=options)
        target = _destination(source, destination)

        entry = None
        if rollback is None:
            self.runtime.debug("rollback-capable move executed without journal")
        else:
            self.runtime.debug(
                "transaction mutation journal=%s operation=move source=%s target=%s",
                rollback,
                source,
                target,
            )
            entry = self.runtime.journal.prepare_paths(
                rollback,
                operation="move",
                paths=(source, target),
                identity=identity,
            )

        if entry is not None:
            self.runtime.journal.mark_mutated(rollback, entry.sequence)

        if not identity.privileged:
            result = _move_local(source, destination)
        else:
            run_as_identity(identity, "mv", source, target)
            result = target

        if entry is not None:
            self.runtime.journal.mark_applied(rollback, entry.sequence)
        return result

    def link(self, source, to, sudo=False, rollback=None, **options):
        """Create a symbolic link to an existing source."""
        source = _path(self.runtime, source)
        destination = _path(self.runtime, to)
        identity = _identity(sudo=sudo, options=options)
        target = _destination(source, destination)

        if not identity.privileged:
            if not source.exists():
                raise FileNotFoundError(source)
            if target.is_symlink() and target.resolve() == source.resolve():
                return target
        else:
            run_as_identity(identity, "test", "-e", source)
            if target.is_symlink() and target.resolve() == source.resolve():
                return target

        if target.exists() or target.is_symlink():
            raise FileExistsError(target)

        entry = None
        if rollback is None:
            self.runtime.debug("rollback-capable link executed without journal")
        else:
            self.runtime.debug(
                "transaction mutation journal=%s operation=link path=%s",
                rollback,
                target,
            )
            entry = self.runtime.journal.prepare_path(
                rollback,
                operation="link",
                path=target,
                identity=identity,
            )

        if entry is not None:
            self.runtime.journal.mark_mutated(rollback, entry.sequence)

        if not identity.privileged:
            result = _link_local(source, destination)
        else:
            run_as_identity(identity, "ln", "-s", source, target)
            result = target

        if entry is not None:
            self.runtime.journal.mark_applied(rollback, entry.sequence)
        return result

    def remove(self, path, sudo=False, rollback=None, **options):
        """Remove a file, symlink, or empty directory."""
        path = _path(self.runtime, path)
        identity = _identity(sudo=sudo, options=options)

        entry = None
        if rollback is None:
            self.runtime.debug("rollback-capable remove executed without journal")
        else:
            self.runtime.debug(
                "transaction mutation journal=%s operation=remove path=%s",
                rollback,
                path,
            )
            entry = self.runtime.journal.prepare_path(
                rollback,
                operation="remove",
                path=path,
                identity=identity,
            )

        if entry is not None:
            self.runtime.journal.mark_mutated(rollback, entry.sequence)

        if not identity.privileged:
            result = _remove_local(path)
        else:
            if path.is_dir() and not path.is_symlink():
                run_as_identity(identity, "rmdir", path)
            else:
                run_as_identity(identity, "rm", "-f", path)
            result = path

        if entry is not None:
            self.runtime.journal.mark_applied(rollback, entry.sequence)
        return result
