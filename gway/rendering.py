"""Generic text template rendering and atomic file replacement."""

import os
from pathlib import Path
import stat
import tempfile
import uuid

from .binding import Literal
from .host import run_as_identity
from .identity import execution_identity
from .recipes import _recipe_base as recipe_base


def _ends_with_separator(value):
    text = str(value)
    return text.endswith(os.sep) or (os.altsep is not None and text.endswith(os.altsep))


def _template_source(runtime, template):
    raw = Path(str(template)).expanduser()
    resolved = Path(str(runtime.resolve(str(template)))).expanduser()
    base = recipe_base(runtime)

    raw_source = raw if raw.is_absolute() else base / raw
    resolved_source = resolved if resolved.is_absolute() else base / resolved

    if raw_source.is_file():
        return raw_source, resolved
    if resolved_source.is_file():
        return resolved_source, resolved

    raise FileNotFoundError(raw_source)


def _destination(runtime, to, resolved_template):
    resolved_text = str(runtime.resolve(str(to)))
    destination = Path(resolved_text).expanduser()

    if (
        destination.is_dir()
        or _ends_with_separator(to)
        or _ends_with_separator(resolved_text)
    ):
        destination = destination / resolved_template.name
    return destination


def _mode_for(destination):
    try:
        return stat.S_IMODE(destination.stat().st_mode)
    except FileNotFoundError:
        return 0o644


def _write_local_atomic(destination, content):
    destination = Path(destination)
    parent = destination.parent
    mode = _mode_for(destination)
    descriptor, temporary = tempfile.mkstemp(
        prefix=f".{destination.name}.gway-",
        dir=parent,
        text=True,
    )
    temporary = Path(temporary)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)


def _write_as_identity(destination, content, identity):
    destination = Path(destination)
    mode = _mode_for(destination)
    target_temporary = destination.with_name(
        f".{destination.name}.gway-{uuid.uuid4().hex}"
    )

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
    ) as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())
        source_temporary = Path(stream.name)

    os.chmod(source_temporary, mode)
    installed = False
    try:
        run_as_identity(
            identity,
            "install",
            "-m",
            f"{mode:04o}",
            source_temporary,
            target_temporary,
        )
        installed = True
        run_as_identity(identity, "mv", "-f", target_temporary, destination)
        installed = False
        run_as_identity(identity, "test", "-f", destination)
    finally:
        source_temporary.unlink(missing_ok=True)
        if installed:
            run_as_identity(
                identity,
                "rm",
                "-f",
                target_temporary,
                check=False,
            )


def atomic_write_text(destination, content, *, identity=None):
    """Atomically replace one text file under an optional execution identity."""
    destination = Path(destination)
    if not destination.parent.is_dir():
        raise FileNotFoundError(destination.parent)

    if identity is None or not identity.privileged:
        _write_local_atomic(destination, content)
        if not destination.is_file():
            raise FileNotFoundError(
                f"Rendered destination was not created: {destination}"
            )
    else:
        _write_as_identity(destination, content, identity)
    return destination


class Renderer:
    """Runtime-bound generic renderer used by the ``render`` operation."""

    def __init__(self, runtime):
        self.runtime = runtime

    def render(self, template: Literal, to, sudo=False, rollback=None, **options):
        """Render a sigil-aware text template to an atomic destination.

        Args:
            template: Template path. Sigils in its filename determine the output name.
            to: Destination file or directory.
            sudo: Execute the final write as root.
            rollback: Optional rollback journal name to capture destination state.
            options: Supports ``--as USER`` for execution identity.
        """
        identity = execution_identity(
            sudo=sudo,
            options=options,
        )
        source, resolved_template = _template_source(self.runtime, template)
        content = source.read_text(encoding="utf-8")
        rendered = self.runtime.resolve(content)
        if not isinstance(rendered, str):
            rendered = str(rendered)

        destination = _destination(self.runtime, to, resolved_template)

        entry = None
        if rollback is not None:
            entry = self.runtime.journal.prepare_path(
                rollback,
                operation="render",
                path=destination,
            )

        result = atomic_write_text(
            destination,
            rendered,
            identity=identity,
        )

        if entry is not None:
            self.runtime.journal.mark_applied(rollback, entry.sequence)

        return result
