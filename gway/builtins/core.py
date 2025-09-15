__all__ = [
    "hello_world",
    "abort",
    "envs",
    "version",
    "shell",
    "upgrade",
]

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

    from gway import gw

    env = os.environ.copy()

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
        "",
        "    if [[ -z \"$exec_path\" ]]; then",
        "        exec_path=\"$(command -v python3 || command -v python || true)\"",
        "    fi",
        "    if [[ -z \"$module\" ]]; then",
        "        module=\"gway\"",
        "    fi",
        "",
        "    if [[ -z \"$GWAY_SHELL_ACTIVE\" && -n \"$exec_path\" ]]; then",
        "        GWAY_SHELL_ACTIVE=1 \"$exec_path\" -m \"$module\" \"${__gway_shell_default_args[@]}\" \"$@\"",
        "        local status=$?",
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

    if status:
        raise SystemExit(status)
    return None


def upgrade(*args):
    """Run ``upgrade.sh`` with the given parameters.

    This mirrors executing the ``upgrade.sh`` script located in the
    installation directory, passing through all provided arguments and
    streaming the script's output as it runs.
    """
    from gway import gw
    import os
    import subprocess
    import sys
    from threading import Thread

    script = gw.resource("upgrade.sh", check=True)
    cmd = ["bash", os.fspath(script), *args]

    def _stream(src, dst):
        for line in src:
            print(line, end="", file=dst, flush=True)

    process = subprocess.Popen(
        cmd,
        cwd=script.parent,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=1,
    )
    threads = [
        Thread(target=_stream, args=(process.stdout, sys.stdout)),
        Thread(target=_stream, args=(process.stderr, sys.stderr)),
    ]
    for t in threads:
        t.start()
    process.wait()
    for t in threads:
        t.join()
    return process.returncode


