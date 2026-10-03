import os
import sqlite3

from tests.bootstrap_support import render_arthexis_bootstrap, run_checked, write_executable


def _write_fake_gway(path):
    write_executable(
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

if args and args[0] == "install":
    if home.exists():
        shutil.rmtree(home)
    shutil.copytree(source, home)
    runtime_bin = home / ".venv" / "bin"
    runtime_bin.mkdir(parents=True, exist_ok=True)
    for executable in ("python", "celery"):
        entrypoint = runtime_bin / executable
        entrypoint.write_text("#!/bin/sh\\nexit 0\\n", encoding="utf-8")
        entrypoint.chmod(0o755)
    raise SystemExit(0)

if args[:2] == ["arthexis", "migrate"]:
    data = Path(os.environ["ARTHEXIS_DATA_DIR"])
    data.mkdir(parents=True, exist_ok=True)
    revision = (home / "revision.txt").read_text(encoding="utf-8").strip()
    with sqlite3.connect(data / "db.sqlite3") as database:
        database.execute("CREATE TABLE IF NOT EXISTS migrations (revision TEXT PRIMARY KEY)")
        database.execute("INSERT OR IGNORE INTO migrations(revision) VALUES (?)", (revision,))
    raise SystemExit(0)

if args[:2] == ["arthexis", "seed"]:
    data = Path(os.environ["ARTHEXIS_DATA_DIR"])
    with sqlite3.connect(data / "db.sqlite3") as database:
        database.execute("CREATE TABLE IF NOT EXISTS payload (value TEXT PRIMARY KEY)")
        database.execute("INSERT OR IGNORE INTO payload(value) VALUES ('seeded')")
    raise SystemExit(0)

if args and args[0] == "service":
    raise SystemExit(0)

raise SystemExit(f"unexpected fake gway invocation: {args!r}")
""",
    )


def _write_fake_systemctl(path):
    write_executable(
        path,
        """#!/bin/sh
case "$*" in
    *" --user is-active --quiet "*|"--user is-active --quiet "*) exit 0 ;;
    *) exit 0 ;;
esac
""",
    )


def test_repeat_bootstrap_preserves_and_backs_up_existing_database(
    sampler_path,
    tmp_path,
):
    bootstrap = tmp_path / "arthexis-bootstrap.sh"
    fake_gway = tmp_path / "gway"
    fake_systemctl = tmp_path / "systemctl"
    candidate = tmp_path / "candidate"
    home = tmp_path / "home" / ".local" / "opt" / "arthexis"
    candidate.mkdir()
    (candidate / "revision.txt").write_text("revision-one\n", encoding="utf-8")
    render_arthexis_bootstrap(sampler_path, bootstrap, yes=False)
    _write_fake_gway(fake_gway)
    _write_fake_systemctl(fake_systemctl)

    env = os.environ.copy()
    env.update(
        {
            "HOME": str(tmp_path / "home"),
            "PATH": f"{tmp_path}{os.pathsep}{env['PATH']}",
            "GWAY_BOOTSTRAP_GWAY": str(fake_gway),
            "ARTHEXIS_BOOTSTRAP_SOURCE": str(candidate),
            "ARTHEXIS_BOOTSTRAP_HOME": str(home),
            "ARTHEXIS_BOOTSTRAP_SHA": "1" * 40,
            "ARTHEXIS_BOOTSTRAP_SERVICE_SETTLE_SECONDS": "0",
        }
    )

    first = run_checked(["sh", str(bootstrap)], env=env)
    database_path = home / "var" / "db.sqlite3"
    assert database_path.is_file()
    assert (home / "revision.txt").read_text(encoding="utf-8") == "revision-one\n"
    assert "Database backup:" not in first.stdout

    with sqlite3.connect(database_path) as database:
        database.execute("INSERT INTO payload(value) VALUES ('field-state')")
        assert database.execute(
            "SELECT revision FROM migrations ORDER BY revision"
        ).fetchall() == [("revision-one",)]

    (candidate / "revision.txt").write_text("revision-two\n", encoding="utf-8")
    env["ARTHEXIS_BOOTSTRAP_SHA"] = "2" * 40
    second = run_checked(["sh", str(bootstrap), "--yes"], env=env)

    assert (home / "revision.txt").read_text(encoding="utf-8") == "revision-two\n"
    assert database_path.is_file()
    with sqlite3.connect(database_path) as database:
        assert database.execute(
            "SELECT value FROM payload ORDER BY value"
        ).fetchall() == [("field-state",), ("seeded",)]
        assert database.execute(
            "SELECT revision FROM migrations ORDER BY revision"
        ).fetchall() == [("revision-one",), ("revision-two",)]

    backups = sorted((home / "var" / "backups").glob("db-*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as backup:
        assert backup.execute(
            "SELECT value FROM payload ORDER BY value"
        ).fetchall() == [("field-state",), ("seeded",)]
        assert backup.execute(
            "SELECT revision FROM migrations ORDER BY revision"
        ).fetchall() == [("revision-one",)]

    assert f"Database backup: {backups[0]}" in second.stdout
