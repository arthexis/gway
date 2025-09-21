__all__ = [
    "hello_world",
    "abort",
    "discard",
    "envs",
    "version",
    "shell",
    "temp_env",
    "install",
    "upgrade",
]

from functools import lru_cache

def hello_world(name: str = "World", *, greeting: str = "Hello", **kwargs):
    """Smoke test function."""
    from gway import gw
    version = gw.version()
    # Preserve the caller's capitalization.  Using ``str.title`` on the
    # arguments caused paths or other case-sensitive values to be modified
    # unexpectedly (e.g. `/home/user/file.py` becoming `/Home/User/File.Py`).
    # Generate the greeting without altering the original casing.
    message = f"{greeting}, {name}!"
    if hasattr(gw, "hello_world"):
        if not gw.silent:
            print(message)
        else:
            print(f"{gw.silent=}")
    else:
        print("Greeting protocol not found ((serious smoke)).")
    return {
        "greeting": greeting,
        "name": name,
        "message": message,
        "version": version,
    }


def abort(message: str, *, exit_code: int = 13) -> int:
    from gway import gw
    """Abort with error message."""
    gw.critical(message)
    print(f"Halting: {message}")
    raise SystemExit(exit_code)


def discard(*names) -> dict:
    """Remove stored results by key and return a summary."""
    from gway import gw

    discarded: dict[str, object] = {}
    missing: list[str] = []
    sentinel = object()

    def _iter_names(values):
        for value in values:
            if value is None:
                continue
            if isinstance(value, (list, tuple, set)):
                yield from _iter_names(value)
                continue
            name = str(value)
            if name:
                yield name

    for name in _iter_names(names):
        value = gw.results.pop(name, sentinel)
        if value is sentinel:
            missing.append(name)
            continue

        discarded[name] = value
        if name in gw.context:
            gw.context.pop(name, None)

    summary: dict[str, object] = {"discarded": discarded}
    if missing:
        summary["missing"] = missing

    return summary


def envs(filter: str | None = None) -> dict:
    """Return environment variables, optionally filtered."""
    import os

    if filter:
        filter = filter.upper()
        return {k: v for k, v in os.environ.items() if filter in k}
    return os.environ.copy()


def version(check: str | None = None) -> str:
    """Return the version of the package."""
    from gway import gw
    import os

    def parse_version(vstr: str):
        parts = vstr.strip().split(".")
        if len(parts) == 1:
            parts = (parts[0], "0", "0")
        elif len(parts) == 2:
            parts = (parts[0], parts[1], "0")
        if len(parts) > 3:
            raise ValueError(
                f"Invalid version format: '{vstr}', expected 'major.minor.patch'"
            )
        return tuple(int(part) for part in parts)

    version_path = gw.resource("VERSION")
    if os.path.exists(version_path):
        with open(version_path, "r") as version_file:
            current_version = version_file.read().strip()
        if check:
            current_tuple = parse_version(current_version)
            required_tuple = parse_version(check)
            if current_tuple < required_tuple:
                raise AssertionError(
                    f"Required version >= {check}, found {current_version}"
                )
        return current_version
    gw.critical("VERSION file not found.")
    return "unknown"


def shell(*bash_args):
    """Launch a Bash shell that treats unknown commands as GWAY invocations."""
    import os
    import shlex
    import shutil
    import subprocess
    import sys
    import tempfile
    from pathlib import Path

    import gway as gway_package
    from gway import gw

    env = os.environ.copy()

    bootstrap_path: str | None = None
    pythonpath_entries: list[str] = []
    package_init = getattr(gway_package, "__file__", None)
    if package_init:
        package_init_path = Path(package_init).resolve()
        package_dir = package_init_path.parent
        package_root = package_dir.parent
        package_root_str = os.fspath(package_root)
        if package_root_str:
            pythonpath_entries.append(package_root_str)

        bootstrap_source = """#!/usr/bin/env python3
import importlib.util
import os
import sys
from pathlib import Path


def _load_module_from_init(init_path: Path):
    package_dir = init_path.parent
    package_root = package_dir.parent
    root_str = os.fspath(package_root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)

    spec = importlib.util.spec_from_file_location(
        "gway",
        os.fspath(init_path),
        submodule_search_locations=[os.fspath(package_dir)],
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["gway"] = module
    loader = spec.loader
    if loader is None:
        raise SystemExit(127)
    loader.exec_module(module)
    return module


def main() -> None:
    package_init_env = os.environ.get("GWAY_SHELL_PACKAGE_INIT")
    if not package_init_env:
        raise SystemExit(127)

    init_path = Path(package_init_env).resolve()
    module = _load_module_from_init(init_path)

    sys.argv = sys.argv[1:]
    result = module.cli_main()
    if result is not None:
        raise SystemExit(result)


if __name__ == "__main__":
    main()
"""

        with tempfile.NamedTemporaryFile(
            "w", delete=False, prefix="gway-shell-bootstrap-", suffix=".py"
        ) as bootstrap_file:
            bootstrap_file.write(bootstrap_source)
            bootstrap_path = bootstrap_file.name

        env["GWAY_SHELL_PACKAGE_INIT"] = os.fspath(package_init_path)
        env["GWAY_SHELL_BOOTSTRAP"] = bootstrap_path

    if pythonpath_entries:
        env["GWAY_SHELL_PYTHONPATH"] = os.pathsep.join(pythonpath_entries)
        env["GWAY_SHELL_PATHSEP"] = os.pathsep

    exec_candidates = [
        getattr(sys, "executable", None),
        getattr(sys, "_base_executable", None),
        shutil.which("python3"),
        shutil.which("python"),
    ]
    exec_path = next((candidate for candidate in exec_candidates if candidate), "python3")

    default_args = []
    project_path = getattr(gw, "project_path", None)
    if project_path:
        default_args.extend(["-p", project_path])

    client_name = env.get("CLIENT")
    if client_name:
        default_args.extend(["-c", client_name])

    server_name = env.get("SERVER")
    if server_name:
        default_args.extend(["-s", server_name])

    if getattr(gw, "debug_enabled", False):
        default_args.append("-d")
    if getattr(gw, "verbose_enabled", False):
        default_args.append("-v")
    if getattr(gw, "silent_enabled", False):
        default_args.append("-z")
    if getattr(gw, "wizard_enabled", False):
        default_args.append("-w")
    if getattr(gw, "timed_enabled", False):
        default_args.append("-t")

    username = getattr(gw, "name", None)
    if username and username != "gw":
        default_args.extend(["-u", username])

    default_args_literal = " ".join(shlex.quote(arg) for arg in default_args)

    rc_lines = [
        "# GWAY shell bootstrap",
        f"__gway_shell_default_args=({default_args_literal})",
        "",
        "if [[ -n \"$GWAY_ORIGINAL_BASH_ENV\" && -f \"$GWAY_ORIGINAL_BASH_ENV\" ]]; then",
        "    source \"$GWAY_ORIGINAL_BASH_ENV\"",
        "fi",
        "",
        "if [[ $- == *i* ]]; then",
        "    if [[ -n \"$HOME\" && -f \"$HOME/.bashrc\" ]]; then",
        "        source \"$HOME/.bashrc\"",
        "    fi",
        "fi",
        "",
        "command_not_found_handle() {",
        "    local cmd=\"$1\"",
        "",
        "    if [[ -z \"$cmd\" ]]; then",
        "        return 127",
        "    fi",
        "",
        "    local exec_path=\"${GWAY_SHELL_EXEC:-}\"",
        "    local module=\"${GWAY_SHELL_MODULE:-gway}\"",
        "    local bootstrap=\"${GWAY_SHELL_BOOTSTRAP:-}\"",
        "    local extra_pythonpath=\"${GWAY_SHELL_PYTHONPATH:-}\"",
        "    local pathsep=\"${GWAY_SHELL_PATHSEP:-:}\"",
        "    local combined_pythonpath=\"$extra_pythonpath\"",
        "",
        "    if [[ -z \"$exec_path\" ]]; then",
        "        exec_path=\"$(command -v python3 || command -v python || true)\"",
        "    fi",
        "    if [[ -z \"$module\" ]]; then",
        "        module=\"gway\"",
        "    fi",
        "",
        "    if [[ -n \"$PYTHONPATH\" ]]; then",
        "        if [[ -n \"$combined_pythonpath\" ]]; then",
        "            combined_pythonpath+=\"$pathsep$PYTHONPATH\"",
        "        else",
        "            combined_pythonpath=\"$PYTHONPATH\"",
        "        fi",
        "    fi",
        "",
        "    if [[ -z \"$GWAY_SHELL_ACTIVE\" && -n \"$exec_path\" ]]; then",
        "        local status",
        "        if [[ -n \"$bootstrap\" && -f \"$bootstrap\" ]]; then",
        "            if [[ -n \"$combined_pythonpath\" ]]; then",
        "                PYTHONPATH=\"$combined_pythonpath\" GWAY_SHELL_ACTIVE=1 \"$exec_path\" \"$bootstrap\" gway \"${__gway_shell_default_args[@]}\" \"$@\"",
        "            else",
        "                GWAY_SHELL_ACTIVE=1 \"$exec_path\" \"$bootstrap\" gway \"${__gway_shell_default_args[@]}\" \"$@\"",
        "            fi",
        "            status=$?",
        "        else",
        "            if [[ -n \"$combined_pythonpath\" ]]; then",
        "                PYTHONPATH=\"$combined_pythonpath\" GWAY_SHELL_ACTIVE=1 \"$exec_path\" -m \"$module\" \"${__gway_shell_default_args[@]}\" \"$@\"",
        "            else",
        "                GWAY_SHELL_ACTIVE=1 \"$exec_path\" -m \"$module\" \"${__gway_shell_default_args[@]}\" \"$@\"",
        "            fi",
        "            status=$?",
        "        fi",
        "        if [[ $status -ne 127 ]]; then",
        "            return $status",
        "        fi",
        "    fi",
        "",
        "    if [[ -z \"$exec_path\" ]]; then",
        "        printf 'gway-shell: unable to locate Python interpreter for %s\\n' \"$cmd\" >&2",
        "    else",
        "        printf '%s: %s: command not found\\n' \"${0##*/}\" \"$cmd\" >&2",
        "    fi",
        "    return 127",
        "}",
    ]
    rc_contents = "\n".join(rc_lines)

    with tempfile.NamedTemporaryFile("w", delete=False, prefix="gway-shell-", suffix=".sh") as rc_file:
        rc_file.write(rc_contents + "\n")
        rc_path = rc_file.name

    original_bash_env = env.get("BASH_ENV")

    env.update({
        "GWAY_SHELL_EXEC": exec_path,
        "GWAY_SHELL_MODULE": "gway",
        "BASH_ENV": rc_path,
    })

    if original_bash_env:
        env["GWAY_ORIGINAL_BASH_ENV"] = original_bash_env

    cmd = ["bash", "--rcfile", rc_path]
    bash_args = list(bash_args)
    if bash_args and bash_args[0] == "--":
        bash_args = bash_args[1:]
    if bash_args:
        cmd.extend(bash_args)
    else:
        cmd.append("-i")

    try:
        status = subprocess.call(cmd, env=env)
    finally:
        try:
            os.unlink(rc_path)
        except FileNotFoundError:
            pass
        if bootstrap_path:
            try:
                os.unlink(bootstrap_path)
            except FileNotFoundError:
                pass

    if status:
        raise SystemExit(status)
    return None


def temp_env(
    *command,
    packages: str | list[str] | None = None,
    recipe: str | None = None,
    python: str | None = None,
    pip_args: str | list[str] | None = None,
    keep: bool = False,
    check: bool = True,
    capture_output: bool = False,
    cwd: str | None = None,
):
    """Run commands in an isolated throw-away GWAY installation.

    The helper creates a temporary virtual environment, installs the requested
    ``packages`` (defaulting to the latest ``gway`` release) and then executes
    either the provided positional command or the recipe referenced via
    ``--recipe``.  Pass an empty string for ``packages`` to skip the installation
    step entirely.  ``pip_args`` allows forwarding custom flags such as
    ``--no-cache-dir`` to the installation command.  The environment is removed
    automatically unless ``keep`` is ``True``.  A mapping describing the
    executed command, return code and any captured output is returned so
    callers can inspect the run.
    """

    from gway import gw

    import os
    import shlex
    import shutil
    import subprocess
    import sys
    import tempfile
    import venv

    def _split(value: str | list[str] | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            value = value.strip()
            if not value:
                return []
            return shlex.split(value)
        return list(value)

    if len(command) == 1 and isinstance(command[0], (list, tuple)):
        command_args = tuple(command[0])
    else:
        command_args = command

    if command_args and recipe:
        raise ValueError("Provide either positional command arguments or --recipe, not both")
    if not command_args and not recipe:
        raise ValueError("A command or --recipe must be provided")

    packages_list = _split(packages) if packages is not None else ["gway"]
    pip_args_list = _split(pip_args)

    python_exec = python or sys.executable
    temp_root = tempfile.mkdtemp(prefix="gway-temp-env-")
    venv_dir = os.path.join(temp_root, "venv")
    gw.debug(f"temp_env: creating virtualenv at {venv_dir} using {python_exec!r}")

    if python and os.path.abspath(python) != os.path.abspath(sys.executable):
        subprocess.run([python_exec, "-m", "venv", venv_dir], check=True)
    else:
        builder = venv.EnvBuilder(with_pip=True, clear=True)
        builder.create(venv_dir)

    bin_dir = "Scripts" if os.name == "nt" else "bin"
    python_bin = os.path.join(venv_dir, bin_dir, "python")

    try:
        if packages_list:
            pip_cmd = [python_bin, "-m", "pip", "install", "--upgrade", *pip_args_list, *packages_list]
            gw.debug(f"temp_env: installing packages via {pip_cmd!r}")
            subprocess.run(pip_cmd, check=True)
        else:
            gw.debug("temp_env: skipping pip install because no packages were specified")

        run_env = os.environ.copy()
        bin_path = os.path.join(venv_dir, bin_dir)
        run_env["VIRTUAL_ENV"] = venv_dir
        run_env["PATH"] = os.pathsep.join([bin_path, run_env.get("PATH", "")])

        if recipe is not None:
            run_cmd = [python_bin, "-m", "gway", "-r", recipe]
        else:
            run_cmd = list(command_args)
            if run_cmd and run_cmd[0] == "gway":
                run_cmd = [python_bin, "-m", "gway", *run_cmd[1:]]

        run_cwd = cwd or temp_root
        gw.debug(f"temp_env: running command {run_cmd!r} in {run_cwd}")
        run_kwargs: dict[str, object] = {
            "env": run_env,
            "cwd": run_cwd,
            "check": check,
        }
        if capture_output:
            run_kwargs["capture_output"] = True
            run_kwargs["text"] = True

        result = subprocess.run(run_cmd, **run_kwargs)

        response: dict[str, object] = {
            "returncode": result.returncode,
            "env": temp_root,
            "command": run_cmd,
        }
        if capture_output:
            response["stdout"] = result.stdout
            response["stderr"] = result.stderr
        return response
    finally:
        if keep:
            gw.info(f"Temporary environment preserved at {temp_root}")
        else:
            shutil.rmtree(temp_root, ignore_errors=True)

@lru_cache(maxsize=1)
def _package_project():
    from gway.projects.package import gway as package_gway

    return package_gway


def install(
    recipe: str | None = None,
    *recipe_args,
    repair: bool = False,
    remove: bool = False,
    bin: bool = False,
    shell: bool = False,
    force: bool = False,
    debug: bool = False,
    root: bool = False,
    mode: str = "script",
    latest: bool | str | None = None,
    quiet: bool | str | None = True,
) -> int:
    """Run ``install.sh`` or upgrade packages via ``pip``."""

    project = _package_project()
    return project.install_builtin(
        recipe,
        *recipe_args,
        repair=repair,
        remove=remove,
        bin=bin,
        shell=shell,
        force=force,
        debug=debug,
        root=root,
        mode=mode,
        latest=latest,
        quiet=quiet,
    )


def upgrade(*args):
    """Run ``upgrade.sh`` with the given parameters."""

    project = _package_project()
    return project.upgrade_builtin(*args, _temp_env=temp_env)



