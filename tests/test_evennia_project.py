from __future__ import annotations

import io
import types

import pytest

from gway import gw
from gway.projects import evennia


class DummyStdout:
    def __init__(self, lines: list[str]):
        self._iterator = iter(lines)
        self.closed = False

    def __iter__(self):
        return self

    def __next__(self):
        return next(self._iterator)

    def close(self):
        self.closed = True


class DummyProcess:
    def __init__(self, lines: list[str]):
        self.stdout = DummyStdout(lines)
        self._waits = 0
        self.terminated = False
        self.killed = False

    def wait(self, timeout: float | None = None):
        self._waits += 1
        return 0

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class DummyTelnet:
    def __init__(self, *, outputs: list[bytes] | None = None, fail_first_write: bool = False):
        self.outputs = outputs or []
        self.fail_first_write = fail_first_write
        self.writes: list[bytes] = []
        self.closed = False
        self._read_calls = 0

    def queue_output(self, text: str) -> None:
        self.outputs.append(text.encode("utf-8"))

    def write(self, data: bytes) -> None:
        if self.fail_first_write:
            self.fail_first_write = False
            raise EOFError("connection dropped")
        self.writes.append(data)

    def read_very_eager(self) -> bytes:
        self._read_calls += 1
        if self.outputs:
            return self.outputs.pop(0)
        return b""

    def close(self) -> None:
        self.closed = True


def test_install_runs_evennia(tmp_path, monkeypatch):
    called = {}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(evennia.shutil, "which", lambda _: "/usr/bin/evennia")
    monkeypatch.setattr(evennia.importlib.util, "find_spec", lambda _: None)

    def fake_run(command, *, check):
        called["command"] = command
        called["check"] = check

        class Completed:
            returncode = 0

        return Completed()

    monkeypatch.setattr(evennia.subprocess, "run", fake_run)

    result = evennia.install("funtown")

    expected_target = tmp_path / "funtown"
    assert called["command"] == ["/usr/bin/evennia", "--init", str(expected_target)]
    assert called["check"] is True
    assert result == {
        "command": ["/usr/bin/evennia", "--init", str(expected_target)],
        "path": str(expected_target),
        "returncode": 0,
    }


def test_install_fails_when_target_exists(tmp_path, monkeypatch):
    target = tmp_path / "exists"
    target.mkdir()

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(evennia.shutil, "which", lambda _: "/usr/bin/evennia")
    monkeypatch.setattr(evennia.importlib.util, "find_spec", lambda _: None)

    with pytest.raises(FileExistsError):
        evennia.install("exists")


def _install_telnet_factory(monkeypatch, factory):
    monkeypatch.setattr(evennia, "_create_telnet", factory)


def _reset_sessions(monkeypatch):
    monkeypatch.setattr(evennia, "_sessions", {})
    monkeypatch.setattr(evennia, "_default_login", None)


def test_start_streams_output(tmp_path, monkeypatch, capsys):
    lines = ["Starting server\n", "Server ready\n"]
    spawned = {}

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(evennia.shutil, "which", lambda _: "/usr/bin/evennia")
    monkeypatch.setattr(evennia.importlib.util, "find_spec", lambda _: None)
    _reset_sessions(monkeypatch)

    telnet_instances: list[DummyTelnet] = []

    def fake_telnet(host, port, timeout):
        telnet = DummyTelnet()
        telnet_instances.append(telnet)
        return telnet

    _install_telnet_factory(monkeypatch, fake_telnet)

    def fake_popen(command, *, cwd, stdout, stderr, text, bufsize):
        spawned.update(
            {
                "command": command,
                "cwd": cwd,
                "stdout": stdout,
                "stderr": stderr,
                "text": text,
                "bufsize": bufsize,
            }
        )
        return DummyProcess(lines)

    monkeypatch.setattr(evennia.subprocess, "Popen", fake_popen)

    result = evennia.start()

    captured = capsys.readouterr()
    assert captured.out == "".join(lines)
    assert result == {
        "command": ["/usr/bin/evennia", "start"],
        "returncode": 0,
        "login": None,
        "inputs": [],
        "outputs": [],
    }
    assert spawned["cwd"] == str(tmp_path)
    assert spawned["stdout"] is evennia.subprocess.PIPE
    assert spawned["stderr"] is evennia.subprocess.STDOUT
    assert spawned["text"] is True
    assert spawned["bufsize"] == 1
    assert telnet_instances == []


def test_evennia_command_requires_install(monkeypatch):
    monkeypatch.setattr(evennia.shutil, "which", lambda _: None)
    monkeypatch.setattr(evennia.importlib.util, "find_spec", lambda _: None)

    with pytest.raises(RuntimeError):
        evennia._resolve_evennia_command()


def test_start_with_login_creates_session(tmp_path, monkeypatch):
    lines = ["Booting\n"]

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(evennia.shutil, "which", lambda _: "/usr/bin/evennia")
    monkeypatch.setattr(evennia.importlib.util, "find_spec", lambda _: None)
    _reset_sessions(monkeypatch)

    telnet_instances: list[DummyTelnet] = []

    def fake_telnet(host, port, timeout):
        telnet = DummyTelnet()
        telnet_instances.append(telnet)
        return telnet

    _install_telnet_factory(monkeypatch, fake_telnet)

    monkeypatch.setattr(evennia.subprocess, "Popen", lambda *a, **k: DummyProcess(lines))

    result = evennia.start(login="tester")

    assert result["login"] == "tester"
    assert result["inputs"][:2] == ["create tester tester", "connect tester tester"]
    assert len(telnet_instances) == 1
    assert telnet_instances[0].writes[:2] == [
        b"create tester tester\n",
        b"connect tester tester\n",
    ]
    assert evennia._default_login == "tester"


def test_read_returns_buffer(monkeypatch):
    _reset_sessions(monkeypatch)

    telnet = DummyTelnet(outputs=[b"Welcome adventurer\n"])

    def fake_telnet(host, port, timeout):
        return telnet

    _install_telnet_factory(monkeypatch, fake_telnet)

    session = evennia.EvenniaSession("hero")
    evennia._sessions["hero"] = session
    evennia._default_login = "hero"

    result = evennia.read()

    assert result["login"] == "hero"
    assert result["buffer"] == "Welcome adventurer\n"
    assert result["outputs"][-1] == "Welcome adventurer\n"


def test_write_sends_command(monkeypatch):
    _reset_sessions(monkeypatch)

    telnet = DummyTelnet(outputs=[b"You see nothing special.\n"])

    def fake_telnet(host, port, timeout):
        return telnet

    _install_telnet_factory(monkeypatch, fake_telnet)

    session = evennia.EvenniaSession("hero")
    evennia._sessions["hero"] = session
    evennia._default_login = "hero"

    result = evennia.write("look")

    assert telnet.writes[-1] == b"look\n"
    assert "look" in result["inputs"]
    assert result["buffer"] == "You see nothing special.\n"


def test_read_with_new_login_creates_session(monkeypatch):
    _reset_sessions(monkeypatch)

    telnet_instances: list[DummyTelnet] = []

    def fake_telnet(host, port, timeout):
        telnet = DummyTelnet()
        telnet_instances.append(telnet)
        return telnet

    _install_telnet_factory(monkeypatch, fake_telnet)

    result = evennia.read(login="alt")

    assert result["login"] == "alt"
    assert evennia._default_login == "alt"
    assert len(telnet_instances) == 1
    assert telnet_instances[0].writes[:2] == [
        b"create alt alt\n",
        b"connect alt alt\n",
    ]


def test_write_reconnects_on_disconnect(monkeypatch):
    _reset_sessions(monkeypatch)

    telnet_first = DummyTelnet(fail_first_write=True)
    telnet_second = DummyTelnet(outputs=[b"Reconnected.\n"])
    created = iter([telnet_first, telnet_second])

    def fake_telnet(host, port, timeout):
        return next(created)

    _install_telnet_factory(monkeypatch, fake_telnet)

    session = evennia.EvenniaSession("hero")
    evennia._sessions["hero"] = session
    evennia._default_login = "hero"

    result = evennia.write("look")

    assert telnet_first.closed is True
    assert telnet_second.writes[0] == b"connect hero hero\n"
    assert telnet_second.writes[-1] == b"look\n"
    assert "look" in result["inputs"]
    assert result["buffer"] == "Reconnected.\n"


def test_shell_requires_interactive(monkeypatch):
    _reset_sessions(monkeypatch)

    telnet = DummyTelnet()

    def fake_telnet(host, port, timeout):
        return telnet

    _install_telnet_factory(monkeypatch, fake_telnet)

    monkeypatch.setattr(gw, "interactive_enabled", False)

    with pytest.raises(RuntimeError):
        evennia.shell(login="hero", input_stream=io.StringIO(""), output_stream=io.StringIO())


def test_shell_sends_commands_and_reads_output(monkeypatch):
    _reset_sessions(monkeypatch)

    telnet = DummyTelnet(outputs=[b"Welcome!\n"])

    def write_with_response(self, data: bytes) -> None:
        self.writes.append(data)
        if data == b"look\n":
            self.outputs.append(b"You see nothing special.\n")

    telnet.write = types.MethodType(write_with_response, telnet)

    def fake_telnet(host, port, timeout):
        return telnet

    _install_telnet_factory(monkeypatch, fake_telnet)

    monkeypatch.setattr(gw, "interactive_enabled", True)

    input_stream = io.StringIO("look\n")
    output_stream = io.StringIO()

    result = evennia.shell(
        login="hero",
        input_stream=input_stream,
        output_stream=output_stream,
        prompt="> ",
    )

    assert telnet.writes[-1] == b"look\n"
    assert "You see nothing special.\n" in output_stream.getvalue()
    assert result["commands"] == ["look"]
    assert result["gway_results"] == []
    assert result["reason"] == "eof"


def test_shell_runs_gway_command(monkeypatch):
    _reset_sessions(monkeypatch)

    telnet = DummyTelnet()

    def fake_telnet(host, port, timeout):
        return telnet

    _install_telnet_factory(monkeypatch, fake_telnet)

    monkeypatch.setattr(gw, "interactive_enabled", True)

    captured: dict[str, object] = {}

    def fake_process(command_sources, *, origin, gw_instance, **context):
        captured["command_sources"] = command_sources
        captured["gw_instance"] = gw_instance
        return ["ignored"], "Hello world"

    monkeypatch.setattr(evennia.gway_console, "process", fake_process)

    output_stream = io.StringIO()

    result = evennia.shell(
        login="hero",
        input_stream=io.StringIO(">clock.now\n"),
        output_stream=output_stream,
        prompt="",
    )

    assert captured["command_sources"] == [["clock.now"]]
    assert captured["gw_instance"] is gw
    assert "Hello world" in output_stream.getvalue()
    assert result["commands"] == []
    assert result["gway_results"] == [
        {"command": "clock.now", "tokens": ["clock.now"], "result": "Hello world"}
    ]


def test_shell_resolves_sigils_in_commands(monkeypatch):
    _reset_sessions(monkeypatch)

    telnet = DummyTelnet()

    def fake_telnet(host, port, timeout):
        return telnet

    _install_telnet_factory(monkeypatch, fake_telnet)

    monkeypatch.setattr(gw, "interactive_enabled", True)
    gw.results.clear()
    gw.results.update({"direction": "north"})

    evennia.shell(
        login="hero",
        input_stream=io.StringIO("go [direction]\n"),
        output_stream=io.StringIO(),
        prompt="",
    )

    assert telnet.writes[-1] == b"go north\n"
    gw.results.clear()


def test_shell_resolves_sigils_in_gway_commands(monkeypatch):
    _reset_sessions(monkeypatch)

    telnet = DummyTelnet()

    def fake_telnet(host, port, timeout):
        return telnet

    _install_telnet_factory(monkeypatch, fake_telnet)

    monkeypatch.setattr(gw, "interactive_enabled", True)
    gw.results.clear()
    gw.results.update({"task": "status"})

    captured: dict[str, object] = {}

    def fake_process(command_sources, *, origin, gw_instance, **context):
        captured["command_sources"] = command_sources
        captured["gw_instance"] = gw_instance
        return [], "ok"

    monkeypatch.setattr(evennia.gway_console, "process", fake_process)

    evennia.shell(
        login="hero",
        input_stream=io.StringIO(">[task]\n"),
        output_stream=io.StringIO(),
        prompt="",
    )

    assert captured["command_sources"] == [["status"]]
    assert captured["gw_instance"] is gw
    gw.results.clear()

