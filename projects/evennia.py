# file: projects/evennia.py
"""Helpers for working with Evennia game servers.

The functions here wrap the Evennia command line utilities so the
``gway`` CLI can bootstrap and manage game instances.
"""

from __future__ import annotations

import importlib.util
import shlex
import shutil
import subprocess
import sys
import telnetlib
from pathlib import Path
from typing import Iterable, TextIO

import gway.console as gway_console
from gway import gw


def _resolve_evennia_command(*, python: str | None = None) -> list[str]:
    """Return the command sequence to invoke Evennia.

    Preference order:
    1. Explicit ``python`` interpreter provided by the caller.
    2. The ``evennia`` executable available on ``PATH``.
    3. ``python -m evennia`` using the current interpreter, if the module
       is importable.
    """

    if python:
        return [python, "-m", "evennia"]

    executable = shutil.which("evennia")
    if executable:
        return [executable]

    if importlib.util.find_spec("evennia") is not None:
        return [sys.executable, "-m", "evennia"]

    raise RuntimeError(
        "Evennia is not installed. Install it with 'pip install evennia' first."
    )


def install(path: str, *, python: str | None = None) -> dict[str, object]:
    """Initialize a new Evennia game in ``path`` relative to the CWD."""

    target = Path(path)
    if not target.is_absolute():
        target = Path.cwd() / target
    target = target.resolve()

    if target.exists():
        raise FileExistsError(f"Target already exists: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)

    command = _resolve_evennia_command(python=python) + ["--init", str(target)]
    completed = subprocess.run(command, check=True)

    return {
        "command": command,
        "path": str(target),
        "returncode": completed.returncode,
    }


def _drain_output(stream: Iterable[str]) -> None:
    """Print each line coming from ``stream`` as it arrives."""

    for line in stream:
        print(line, end="", flush=True)


def _realize_result(value: object) -> object:
    """Materialize iterable results into lists for stable presentation."""

    if isinstance(value, (str, bytes, dict)) or value is None:
        return value
    if hasattr(value, "__iter__"):
        try:
            return list(value)
        except Exception:
            return value
    return value


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 4000
DEFAULT_TIMEOUT = 5.0


def _create_telnet(host: str, port: int, timeout: float) -> telnetlib.Telnet:
    """Factory for ``telnetlib.Telnet`` so tests can stub it easily."""

    return telnetlib.Telnet(host=host, port=port, timeout=timeout)


class EvenniaSession:
    """Manage a telnet connection for a specific Evennia character."""

    def __init__(
        self,
        login: str,
        *,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        password: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.login = login
        self.host = host
        self.port = port
        self.timeout = timeout
        self.password = password if password is not None else login
        self.inputs: list[str] = []
        self.outputs: list[str] = []
        self._telnet: telnetlib.Telnet | None = None
        self._ever_connected = False

        self._connect(create=True)

    def close(self) -> None:
        """Close the underlying telnet connection."""

        self._disconnect()

    def send_line(self, command: str) -> None:
        """Send ``command`` to the server, adding a newline automatically."""

        line = command.rstrip("\n") + "\n"
        self._perform_write(line, log=True)

    def collect(self) -> str:
        """Gather all available output from the server."""

        data: list[str] = []
        while True:
            chunk = self._perform_read()
            if not chunk:
                break
            data.append(chunk)

        combined = "".join(data)
        if combined:
            self.outputs.append(combined)
        return combined

    def _connect(self, *, create: bool) -> None:
        self._telnet = _create_telnet(self.host, self.port, self.timeout)
        self._ever_connected = True
        self._login(create=create)

    def _disconnect(self) -> None:
        telnet = self._telnet
        if telnet is not None:
            try:
                telnet.close()
            finally:
                self._telnet = None

    def _login(self, *, create: bool) -> None:
        if create:
            self._perform_write(
                f"create {self.login} {self.password}\n",
                log=True,
            )
        self._perform_write(
            f"connect {self.login} {self.password}\n",
            log=True,
        )

    def _perform_write(self, message: str, *, log: bool) -> None:
        attempts = 0
        while True:
            attempts += 1
            if self._telnet is None:
                self._connect(create=not self._ever_connected)
            assert self._telnet is not None  # mypy appeasement, covered by connect above
            try:
                self._telnet.write(message.encode("utf-8"))
                if log:
                    self.inputs.append(message.rstrip("\n"))
                return
            except (EOFError, ConnectionResetError, OSError):
                self._disconnect()
                if attempts >= 3:
                    raise
                self._connect(create=False)

    def _perform_read(self) -> str:
        attempts = 0
        while True:
            attempts += 1
            if self._telnet is None:
                self._connect(create=not self._ever_connected)
            assert self._telnet is not None
            try:
                raw = self._telnet.read_very_eager()
            except (EOFError, ConnectionResetError, OSError):
                self._disconnect()
                if attempts >= 3:
                    raise
                self._connect(create=False)
                continue
            if not raw:
                return ""
            decoded = raw.decode("utf-8", errors="replace")
            return decoded


_sessions: dict[str, EvenniaSession] = {}
_default_login: str | None = None


def _obtain_session(
    login: str | None,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    password: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    create: bool,
    replace: bool = False,
) -> EvenniaSession:
    """Return the ``EvenniaSession`` associated with ``login``."""

    global _default_login

    key = login if login is not None else _default_login
    if key is None:
        raise RuntimeError("No Evennia session is active. Provide --login to create one.")

    session = _sessions.get(key)
    if session is not None and replace:
        session.close()
        session = None

    if session is None:
        if not create:
            raise RuntimeError(
                f"No Evennia session for login {key!r}. Provide --login to create it first."
            )
        session = EvenniaSession(
            key,
            host=host,
            port=port,
            password=password,
            timeout=timeout,
        )
        _sessions[key] = session

    if _default_login is None:
        _default_login = session.login

    return session


def start(
    *,
    python: str | None = None,
    login: str | None = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    password: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, object]:
    """Start the Evennia instance in the current working directory.

    The call blocks while the server is running and mirrors the output so the
    CLI stays attached to the process.
    """

    command = _resolve_evennia_command(python=python) + ["start"]
    session: EvenniaSession | None = None
    if login:
        session = _obtain_session(
            login,
            host=host,
            port=port,
            password=password,
            timeout=timeout,
            create=True,
            replace=True,
        )

    process = subprocess.Popen(  # noqa: S603
        command,
        cwd=str(Path.cwd()),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    stdout = process.stdout

    try:
        if stdout is not None:
            _drain_output(stdout)
        returncode = process.wait()
    except KeyboardInterrupt:  # pragma: no cover - exercised manually
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        raise
    finally:
        if stdout is not None:
            stdout.close()

    result: dict[str, object] = {
        "command": command,
        "returncode": returncode,
        "login": login,
        "inputs": session.inputs.copy() if session else [],
        "outputs": session.outputs.copy() if session else [],
    }
    return result


def read(
    *,
    login: str | None = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    password: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, object]:
    """Fetch buffered output for ``login`` or the default session."""

    session = _obtain_session(
        login,
        host=host,
        port=port,
        password=password,
        timeout=timeout,
        create=login is not None,
    )
    buffer = session.collect()
    return {
        "login": session.login,
        "buffer": buffer,
        "inputs": session.inputs.copy(),
        "outputs": session.outputs.copy(),
    }


def write(
    command: str,
    *,
    login: str | None = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    password: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, object]:
    """Send ``command`` to ``login``'s session and return captured output."""

    session = _obtain_session(
        login,
        host=host,
        port=port,
        password=password,
        timeout=timeout,
        create=login is not None,
    )
    session.send_line(command)
    buffer = session.collect()
    return {
        "login": session.login,
        "command": command,
        "buffer": buffer,
        "inputs": session.inputs.copy(),
        "outputs": session.outputs.copy(),
    }


def shell(
    *,
    login: str | None = None,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    password: str | None = None,
    timeout: float = DEFAULT_TIMEOUT,
    prompt: str = "evennia> ",
    gway_prefix: str = ">",
    input_stream: TextIO | None = None,
    output_stream: TextIO | None = None,
) -> dict[str, object]:
    """Run an interactive Evennia session with optional Gateway command support."""

    if not gw.interactive_enabled:
        raise RuntimeError("Evennia shell requires interactive mode. Run with `-i`.")

    session = _obtain_session(
        login,
        host=host,
        port=port,
        password=password,
        timeout=timeout,
        create=login is not None,
    )

    stdin = input_stream if input_stream is not None else sys.stdin
    stdout = output_stream if output_stream is not None else sys.stdout

    def write_output(text: str) -> None:
        stdout.write(text)
        stdout.flush()

    def resolve_text(text: str) -> str:
        if text and "[" in text and "]" in text:
            resolved = gw.resolve(text)
            return resolved if isinstance(resolved, str) else str(resolved)
        return text

    exit_reason = "eof"
    user_commands: list[str] = []
    gway_results: list[dict[str, object]] = []

    while True:
        buffer = session.collect()
        if buffer:
            write_output(buffer)

        if prompt:
            write_output(prompt)

        try:
            line = stdin.readline()
        except KeyboardInterrupt:
            exit_reason = "interrupt"
            write_output("\n")
            break

        if line == "":
            if prompt:
                write_output("\n")
            break

        line = line.rstrip("\r\n")
        if not line.strip():
            continue

        stripped = line.lstrip()
        is_gway_command = gway_prefix and stripped.startswith(gway_prefix)

        if is_gway_command:
            command_text = stripped[len(gway_prefix) :].lstrip()
            if not command_text:
                continue
            try:
                command_text = resolve_text(command_text)
            except KeyError as exc:
                write_output(f"{exc}\n")
                continue
            try:
                tokens = shlex.split(command_text)
            except ValueError as exc:
                write_output(f"Error parsing gway command: {exc}\n")
                continue
            if not tokens:
                continue
            try:
                _, last_result = gway_console.process(
                    [tokens],
                    origin="line",
                    gw_instance=gw,
                )
            except Exception as exc:  # pragma: no cover - defensive
                write_output(f"Error running gway command: {exc}\n")
                continue

            realized = _realize_result(last_result)
            if realized is not None:
                display = realized if isinstance(realized, str) else str(realized)
                if display:
                    write_output(display)
                    if not display.endswith("\n"):
                        write_output("\n")

            gway_results.append(
                {
                    "command": command_text,
                    "tokens": tokens.copy(),
                    "result": realized,
                }
            )
            continue

        try:
            resolved_command = resolve_text(line)
        except KeyError as exc:
            write_output(f"{exc}\n")
            continue

        if not resolved_command:
            continue

        session.send_line(resolved_command)
        user_commands.append(resolved_command)

        buffer = session.collect()
        if buffer:
            write_output(buffer)

    return {
        "login": session.login,
        "commands": user_commands,
        "gway_results": gway_results,
        "inputs": session.inputs.copy(),
        "outputs": session.outputs.copy(),
        "reason": exit_reason,
    }

