from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path

SUPPORTED_SHELLS = ("bash", "zsh")
BEGIN_MARKER = "# >>> gway shell integration >>>"
END_MARKER = "# <<< gway shell integration <<<"
ALIAS_LINE = "alias -- -='gway'"
_MANAGED_BLOCK = re.compile(
    rf"(?ms)^{re.escape(BEGIN_MARKER)}\n.*?^{re.escape(END_MARKER)}\n?"
)


class ShellError(ValueError):
    pass


def detect_shell(
    requested: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> str:
    env = os.environ if environ is None else environ
    if requested is not None:
        name = Path(requested).name
        if name not in SUPPORTED_SHELLS:
            supported = ", ".join(SUPPORTED_SHELLS)
            raise ShellError(f"unsupported shell {requested!r}; supported shells: {supported}")
        return name

    configured = Path(env.get("SHELL", "")).name
    if configured in SUPPORTED_SHELLS:
        return configured

    for name in SUPPORTED_SHELLS:
        if shutil.which(name):
            return name

    supported = ", ".join(SUPPORTED_SHELLS)
    raise ShellError(f"could not detect a supported shell; supported shells: {supported}")


def integration_snippet(shell: str | None = None) -> str:
    detect_shell(shell)
    return f"{BEGIN_MARKER}\n{ALIAS_LINE}\n{END_MARKER}\n"


def rc_path(
    shell: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    name = detect_shell(shell, environ=env)
    home = Path(env.get("HOME", str(Path.home()))).expanduser()
    if name == "bash":
        return home / ".bashrc"

    zdotdir = env.get("ZDOTDIR")
    base = Path(zdotdir).expanduser() if zdotdir else home
    return base / ".zshrc"


def _replace_managed_block(text: str, replacement: str) -> tuple[str, bool]:
    if _MANAGED_BLOCK.search(text):
        return _MANAGED_BLOCK.sub(replacement, text, count=1), True

    prefix = text
    if prefix and not prefix.endswith("\n"):
        prefix += "\n"
    return prefix + replacement, False


def install_shell(
    shell: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    env = os.environ if environ is None else environ
    name = detect_shell(shell, environ=env)
    path = rc_path(name, environ=env)
    current = path.read_text(encoding="utf-8") if path.exists() else ""
    updated, replaced = _replace_managed_block(current, integration_snippet(name))

    if updated != current:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(updated, encoding="utf-8")

    return {
        "status": "installed",
        "shell": name,
        "path": str(path),
        "changed": updated != current,
        "replaced": replaced,
    }


def uninstall_shell(
    shell: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    env = os.environ if environ is None else environ
    name = detect_shell(shell, environ=env)
    path = rc_path(name, environ=env)
    if not path.exists():
        return {
            "status": "not-installed",
            "shell": name,
            "path": str(path),
            "changed": False,
        }

    current = path.read_text(encoding="utf-8")
    updated, count = _MANAGED_BLOCK.subn("", current, count=1)
    if count:
        path.write_text(updated, encoding="utf-8")

    return {
        "status": "uninstalled" if count else "not-installed",
        "shell": name,
        "path": str(path),
        "changed": bool(count),
    }


def shell_status(
    shell: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> dict[str, object]:
    env = os.environ if environ is None else environ
    name = detect_shell(shell, environ=env)
    path = rc_path(name, environ=env)
    installed = (
        path.exists()
        and _MANAGED_BLOCK.search(path.read_text(encoding="utf-8")) is not None
    )
    return {
        "status": "installed" if installed else "not-installed",
        "shell": name,
        "path": str(path),
    }


def _shell_executable(name: str, environ: Mapping[str, str]) -> str:
    configured = environ.get("SHELL")
    if configured and Path(configured).name == name:
        path = Path(configured).expanduser()
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)

    executable = shutil.which(name)
    if executable is None:
        raise ShellError(f"{name} executable not found")
    return executable


def _startup_contents(name: str, original_rc: Path) -> str:
    lines = []
    if original_rc.exists():
        lines.append(f". {shlex.quote(str(original_rc))}")
    lines.extend((ALIAS_LINE, "export GWAY_SHELL=1"))
    return "\n".join(lines) + "\n"


def launch_shell(
    shell: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> int:
    source_env = os.environ if environ is None else environ
    env = dict(source_env)
    name = detect_shell(shell, environ=env)
    executable = _shell_executable(name, env)
    original_rc = rc_path(name, environ=env)

    with tempfile.TemporaryDirectory(prefix="gway-shell-") as temp_dir:
        temp_path = Path(temp_dir)
        startup = _startup_contents(name, original_rc)

        if name == "bash":
            rcfile = temp_path / "bashrc"
            rcfile.write_text(startup, encoding="utf-8")
            command = [executable, "--rcfile", str(rcfile), "-i"]
        else:
            (temp_path / ".zshrc").write_text(startup, encoding="utf-8")
            env["ZDOTDIR"] = str(temp_path)
            command = [executable, "-i"]

        return subprocess.run(command, env=env, check=False).returncode
