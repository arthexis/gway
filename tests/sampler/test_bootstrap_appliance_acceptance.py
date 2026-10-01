import json
import os
import subprocess


def _render_bootstrap(sampler_path, target):
    script = sampler_path("bootstrap/arthexis.sh").read_text(encoding="utf-8")
    script = script.replace("[installer_yes|0]", "1")
    script = script.replace("[installer_title]", "Satellite")
    script = script.replace("[domain]", "install.example.test")
    script = script.replace("[[", "[").replace("]]", "]")
    target.write_text(script, encoding="utf-8")
    target.chmod(0o755)


def _write_executable(path, content):
    path.write_text(content, encoding="utf-8")
    path.chmod(0o755)


def _write_fake_gway(path):
    _write_executable(
        path,
        """#!/usr/bin/env python3
import os
from pathlib import Path
import shutil
import sqlite3
import sys

args = sys.argv[1:]
home = Path(os.environ["ARTHEXIS_BOOTSTRAP_HOME"])
source = Path(os.environ["ARTHEXIS_BOOTSTRAP_SOURCE"])

if args == ["version"]:
    print("1.1.6")
    raise SystemExit(0)

if args and args[0] == "install":
    if home.exists():
        shutil.rmtree(home)
    shutil.copytree(source, home)
    runtime_bin = home / ".venv" / "bin"
    runtime_bin.mkdir(parents=True, exist_ok=True)
    for executable in ("serve", "celery"):
        entrypoint = runtime_bin / executable
        entrypoint.write_text("#!/bin/sh\\nexit 0\\n", encoding="utf-8")
        entrypoint.chmod(0o755)
    raise SystemExit(0)

if args[:2] == ["arthexis", "migrate"]:
    data = Path(os.environ["ARTHEXIS_DATA_DIR"])
    data.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(data / "db.sqlite3") as database:
        database.execute("CREATE TABLE IF NOT EXISTS migrations (revision TEXT PRIMARY KEY)")
    raise SystemExit(0)

if args[:2] == ["arthexis", "seed"]:
    data = Path(os.environ["ARTHEXIS_DATA_DIR"])
    with sqlite3.connect(data / "db.sqlite3") as database:
        database.execute("CREATE TABLE IF NOT EXISTS payload (value TEXT PRIMARY KEY)")
        database.execute("INSERT OR IGNORE INTO payload(value) VALUES ('seeded')")
    raise SystemExit(0)

if args[:2] == ["service", "statuses"]:
    print("web: running")
    print("worker: running")
    print("beat: running")
    raise SystemExit(0)

if args and args[0] == "service":
    raise SystemExit(0)

raise SystemExit(f"unexpected fake gway invocation: {args!r}")
""",
    )


def _write_fake_uv(path):
    _write_executable(
        path,
        """#!/usr/bin/env python3
import os
from pathlib import Path
import shutil
import sys

args = sys.argv[1:]
tool_bin = Path(os.environ["FAKE_TOOL_BIN"])
gway_program = Path(os.environ["FAKE_GWAY_PROGRAM"])

if args == ["tool", "dir", "--bin"]:
    print(tool_bin)
    raise SystemExit(0)

if args[:2] == ["tool", "uninstall"] and args[2:] == ["gway"]:
    (tool_bin / "gway").unlink(missing_ok=True)
    raise SystemExit(0)

if args and args[0] == "venv":
    candidate = Path(args[1])
    (candidate / "bin").mkdir(parents=True, exist_ok=True)
    raise SystemExit(0)

if args[:2] == ["pip", "install"]:
    python_path = Path(args[args.index("--python") + 1])
    target = python_path.parent / "gway"
    shutil.copy2(gway_program, target)
    target.chmod(0o755)
    raise SystemExit(0)

raise SystemExit(f"unexpected fake uv invocation: {args!r}")
""",
    )


def _write_fake_curl(path):
    _write_executable(
        path,
        """#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
if "-o" in args:
    output = Path(args[args.index("-o") + 1])
    output.write_text(
        json.dumps({"arthexis_sha": "a" * 40, "gway_sha": "b" * 40}),
        encoding="utf-8",
    )
    raise SystemExit(0)

print('mkdir -p "$FAKE_TOOL_BIN"')
print('cp "$FAKE_GWAY_PROGRAM" "$FAKE_TOOL_BIN/gway"')
print('chmod 755 "$FAKE_TOOL_BIN/gway"')
""",
    )


def _write_fake_privilege_tools(directory):
    _write_executable(
        directory / "sudo",
        """#!/bin/sh
FAKE_ROOT=1 exec "$@"
""",
    )
    _write_executable(
        directory / "id",
        """#!/bin/sh
if test "${1:-}" = "-u"; then
    if test "${FAKE_ROOT:-0}" = 1; then
        echo 0
    else
        echo 1000
    fi
    exit 0
fi
exec /usr/bin/id "$@"
""",
    )


def _write_fake_systemctl(path):
    _write_executable(path, "#!/bin/sh\nexit 0\n")


def _run(command, *, env):
    return subprocess.run(
        command,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_arthexis_bootstrap_is_posix_shell_syntax_valid(sampler_path, tmp_path):
    script = tmp_path / "bootstrap.sh"
    _render_bootstrap(sampler_path, script)

    result = subprocess.run(
        ["sh", "-n", str(script)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


def test_appliance_bootstrap_replaces_split_gway_install_with_one_certified_runtime(
    sampler_path,
    tmp_path,
):
    bootstrap = tmp_path / "bootstrap.sh"
    fake_gway = tmp_path / "fake-gway"
    fake_uv = tmp_path / "uv"
    fake_curl = tmp_path / "curl"
    fake_systemctl = tmp_path / "systemctl"
    tool_bin = tmp_path / "tool-bin"
    system_venv = tmp_path / "opt" / "gway" / "venv"
    system_command = tmp_path / "usr" / "local" / "bin" / "gway"
    system_config = tmp_path / "etc" / "gway"
    system_data = tmp_path / "var" / "lib" / "gway"
    home = tmp_path / "home" / ".local" / "opt" / "arthexis"
    source = tmp_path / "candidate-source"

    _render_bootstrap(sampler_path, bootstrap)
    _write_fake_gway(fake_gway)
    _write_fake_uv(fake_uv)
    _write_fake_curl(fake_curl)
    _write_fake_systemctl(fake_systemctl)
    _write_fake_privilege_tools(tmp_path)

    source.mkdir()
    (source / "revision.txt").write_text("certified\n", encoding="utf-8")

    # Model the stale PyPI-managed system copy that exposed the original bug.
    (system_venv / "bin").mkdir(parents=True)
    _write_executable(
        system_venv / "bin" / "gway",
        "#!/bin/sh\necho 1.0.1\n",
    )
    (system_venv / "stale-marker").write_text("old runtime\n", encoding="utf-8")

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path / "home"),
            "PATH": f"{tmp_path}{os.pathsep}{env['PATH']}",
            "FAKE_TOOL_BIN": str(tool_bin),
            "FAKE_GWAY_PROGRAM": str(fake_gway),
            "ARTHEXIS_BOOTSTRAP_HOME": str(home),
            "ARTHEXIS_BOOTSTRAP_SOURCE": str(source),
            "ARTHEXIS_BOOTSTRAP_SERVICE_SETTLE_SECONDS": "0",
            "GWAY_SYSTEM_VENV": str(system_venv),
            "GWAY_SYSTEM_COMMAND": str(system_command),
            "GWAY_SYSTEM_CONFIG_HOME": str(system_config),
            "GWAY_SYSTEM_DATA_HOME": str(system_data),
        }
    )

    result = _run(["sh", str(bootstrap)], env=env)

    assert "Gway appliance runtime:" in result.stdout
    assert "Satellite installation complete." in result.stdout
    assert not (tool_bin / "gway").exists()
    assert not (system_venv / "stale-marker").exists()
    assert not list(system_venv.parent.glob("venv.previous.*"))
    assert not list(system_venv.parent.glob("venv.candidate.*"))

    assert _run([str(system_command), "version"], env=env).stdout.strip() == "1.1.6"
    assert _run([str(tmp_path / "sudo"), str(system_command), "version"], env=env).stdout.strip() == "1.1.6"

    statuses = _run(
        [str(system_command), "service", "statuses", "--project", "arthexis"],
        env=env,
    ).stdout
    assert "web: running" in statuses
    assert "worker: running" in statuses
    assert "beat: running" in statuses
