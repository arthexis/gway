# file: projects/release.py

import os
import inspect
import threading
import time
import html
import re
import ast
import importlib.util
import getpass
import traceback
import shutil
import stat
import subprocess
import sys
import platform
from datetime import datetime
from pathlib import Path
from io import StringIO
import textwrap
import unittest
from typing import cast

try:
    from coverage import Coverage
except Exception:
    Coverage = None


from gway import gw

# List of project docs relative to data/static
PROJECT_READMES = [
    'awg', 'cdv', 'monitor', 'release',
]


def _git_rev_parse(ref: str) -> str | None:
    """Return the commit hash for *ref*, or ``None`` if it cannot be resolved."""

    try:
        output = subprocess.check_output(
            ["git", "rev-parse", ref],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return None
    return output.strip() or None


def open_notepad(path: os.PathLike[str] | str, *, wait: bool = False) -> subprocess.Popen | None:
    """Open *path* in Windows Notepad when available."""

    if platform.system() != "Windows":
        return None

    target = Path(path)
    try:
        process = subprocess.Popen(["notepad.exe", str(target)])
    except Exception as exc:  # pragma: no cover - depends on host OS
        gw.warning(f"[release] Unable to launch Notepad for {target}: {exc}")
        return None

    if wait:
        try:
            process.wait()
        except Exception as exc:  # pragma: no cover - defensive logging
            gw.debug(f"[release] Waiting on Notepad failed: {exc}")
    return process


def auto_releaser_scan(
    *,
    branch: str = "main",
    remote: str = "origin",
    last_commit: str | None = None,
) -> dict[str, object]:
    """Fetch ``remote/branch`` and report whether a new commit is available."""

    fetch_result = subprocess.run(
        ["git", "fetch", "--all", "--prune"],
        capture_output=True,
        text=True,
    )
    remote_ref = f"{remote}/{branch}"
    head_commit = _git_rev_parse("HEAD")

    status = "updated"
    remote_commit: str | None = None

    if fetch_result.returncode != 0:
        status = "fetch-error"
    else:
        remote_commit = _git_rev_parse(remote_ref)
        if remote_commit is None:
            status = "missing-remote"
        elif last_commit is not None and remote_commit == last_commit:
            status = "unchanged"

    return {
        "status": status,
        "remote_ref": remote_ref,
        "remote_commit": remote_commit,
        "head_commit": head_commit,
        "fetch_result": fetch_result,
    }


def auto_releaser_check(
    *,
    branch: str = "main",
    remote: str = "origin",
    last_commit: str | None = None,
) -> dict[str, object]:
    """Return a summary of the current remote commit state for auto releases."""

    scan = auto_releaser_scan(branch=branch, remote=remote, last_commit=last_commit)
    fetch_result = scan["fetch_result"]
    summary = {
        "status": scan["status"],
        "remote": scan["remote_ref"],
        "remote_commit": scan.get("remote_commit"),
        "head_commit": scan.get("head_commit"),
        "fetch_exit_code": getattr(fetch_result, "returncode", None),
    }
    if isinstance(fetch_result, subprocess.CompletedProcess):
        summary["fetch_stdout"] = (fetch_result.stdout or "").strip() or None
        summary["fetch_stderr"] = (fetch_result.stderr or "").strip() or None
    return summary


def build(
    *,
    bump: bool = False,
    dist: bool = False,
    twine: bool = False,
    help_db: bool = False,
    projects: bool = False,
    git: bool = False,
    notify: bool = False,
    tag: bool = False,
    all: bool = False,
    force: bool = False
) -> None:
    """
    Build the project and optionally upload to PyPI.

    Args:
        bump (bool): Increment patch version if True.
        dist (bool): Build distribution package if True.
        twine (bool): Upload to PyPI if True.
        force (bool): Skip version-exists check on PyPI if True.
        git (bool): Require a clean git repo and commit/push after release if True.
        notify (bool): Show a desktop notification when done.
        tag (bool): Create and push a git tag for the build version.
    """
    from pathlib import Path
    import sys
    import subprocess
    import toml

    interactive_mode = getattr(gw, "interactive_enabled", False)
    wizard_mode = getattr(gw, "wizard_enabled", False)

    def _format_failure_report(exc: BaseException, tb: str) -> str:
        lines = [
            f"GWAY release build failed ({type(exc).__name__}): {exc}",
        ]
        if isinstance(exc, subprocess.CalledProcessError):
            lines.append("")
            lines.append(f"Command: {' '.join(map(str, exc.cmd))}")
            lines.append(f"Return code: {exc.returncode}")
            output = getattr(exc, "stdout", None) or getattr(exc, "stderr", None) or getattr(exc, "output", None)
            if output:
                if not isinstance(output, str):
                    try:
                        output = output.decode()
                    except Exception:
                        output = str(output)
                lines.append("")
                lines.append("Command output:")
                lines.append(output.strip())
        if tb:
            lines.append("")
            lines.append("Traceback:")
            lines.append(tb.strip())
        return "\n".join(lines)

    def _handle_failure(exc: BaseException, tb: str) -> None:
        if not wizard_mode:
            return
        report = _format_failure_report(exc, tb)

        def _copy_report() -> None:
            try:
                gw.studio.clip.copy(report, notify=False)
            except Exception as copy_err:
                gw.warning(f"Failed to copy failure report: {copy_err}")
            else:
                gw.info("Failure report copied to clipboard.")

        if interactive_mode:
            try:
                response = input("Copy failure report to clipboard? [Y/n] ").strip().lower()
            except EOFError:
                response = "n"
            if response in ("", "y", "yes"):
                _copy_report()
        else:
            gw.info("Wizard mode enabled; copying failure report to clipboard.")
            _copy_report()

    def _prompt_input(message: str, *, secret: bool = False) -> str:
        try:
            raw = getpass.getpass(message) if secret else input(message)
        except EOFError:
            return ""
        return (raw or "").strip()

    def _do_build() -> None:
        nonlocal bump, dist, twine, git, projects, notify, tag

        gw.info("Installing requirements before release build...")
        subprocess.run([
            sys.executable,
            "-m",
            "pip",
            "install",
            "-U",
            "-r",
            "requirements.txt",
        ], check=True)

        if all:
            bump = True
            dist = True
            twine = True
            git = True
            projects = True
            notify = True
            tag = True

        gw.info("Running tests before project build.")
        test_result = gw.test()
        if not test_result:
            gw.abort("Tests failed, build aborted.")

        if git:
            status = subprocess.run(["git", "status", "--porcelain"], capture_output=True, text=True)
            if status.stdout.strip():
                gw.abort("Git repository is not clean. Commit or stash changes before building.")

        if projects:
            project_dir = gw.resource("projects")

        project_name = "gway"
        description = "Software Project Infrastructure by https://www.gelectriic.com"
        author_name = "Rafael J. Guillén-Osorio"
        author_email = "tecnologia@gelectriic.com"
        python_requires = ">=3.10"
        license_expression = "MIT"
        readme_file = Path("README.rst")

        classifiers = [
            "Programming Language :: Python :: 3",
            "Operating System :: OS Independent",
        ]

        version_path = Path("VERSION")
        requirements_path = Path("requirements.txt")
        pyproject_path = Path("pyproject.toml")

        if not version_path.exists():
            raise FileNotFoundError("VERSION file not found.")
        if not requirements_path.exists():
            raise FileNotFoundError("requirements.txt file not found.")
        if not readme_file.exists():
            raise FileNotFoundError("README.rst file not found.")

        if bump:
            current_version = version_path.read_text().strip()
            major, minor, patch = map(int, current_version.split("."))
            patch += 1
            new_version = f"{major}.{minor}.{patch}"
            version_path.write_text(new_version + "\n")
            gw.info(f"\nBumped version: {current_version} → {new_version}")
        else:
            new_version = version_path.read_text().strip()

        version = new_version

        # Write BUILD file with current commit hash
        build_path = Path("BUILD")
        prev_build = build_path.read_text().strip() if build_path.exists() else None
        build_hash = gw.hub.commit()
        build_path.write_text(build_hash + "\n")
        gw.info(f"Wrote BUILD file with commit {build_hash}")
        update_changelog(version, build_hash, prev_build)

        dependencies = [
            line.strip()
            for line in requirements_path.read_text().splitlines()
            if line.strip() and not line.startswith("#")
        ]

        optional_dependencies = {
            "dev": ["pytest", "pytest-cov"],
        }

        pyproject_content = {
            "build-system": {
                "requires": ["setuptools", "wheel"],
                "build-backend": "setuptools.build_meta",
            },
            "project": {
                "name": project_name,
                "version": version,
                "description": description,
                "requires-python": python_requires,
                "license": license_expression,
                "readme": {
                    "file": "README.rst",
                    "content-type": "text/x-rst"
                },
                "classifiers": classifiers,
                "dependencies": dependencies,
                "optional-dependencies": optional_dependencies,
                "authors": [
                    {
                        "name": author_name,
                        "email": author_email,
                    }
                ],
                "scripts": {
                    project_name: f"{project_name}:cli_main",
                },
                "urls": {
                    "Repository": "https://github.com/arthexis/gway.git",
                    "Homepage": "https://arthexis.com",
                    "Sponsor": "https://www.gelectriic.com/",
                }
            },
            "tool": {
                "setuptools": {
                    "packages": ["gway"],
                }
            }
        }

        pyproject_path.write_text(toml.dumps(pyproject_content), encoding="utf-8")
        gw.info(f"Generated {pyproject_path}")

        if projects:
            update_readme_links()

        manifest_path = Path("MANIFEST.in")
        if not manifest_path.exists():
            manifest_path.write_text(
                "include README.rst\n"
                "include VERSION\n"
                "include BUILD\n"
                "include requirements.txt\n"
                "include pyproject.toml\n"
            )
            gw.info("Generated MANIFEST.in")

        if dist:
            dist_dir = Path("dist")
            if dist_dir.exists():
                gw.info("Cleaning existing dist/ directory before build.")

                def _on_rm_error(func, path_str, exc_info):
                    exc = exc_info[1]
                    if isinstance(exc, PermissionError):
                        try:
                            os.chmod(path_str, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
                        except Exception:
                            pass
                        func(path_str)
                    else:
                        raise exc

                try:
                    shutil.rmtree(dist_dir, onerror=_on_rm_error)
                except Exception as exc:  # pragma: no cover - best effort cleanup
                    gw.warning(f"Could not fully clean dist/: {exc}")
            dist_dir.mkdir(exist_ok=True)

            gw.info("Building distribution package...")
            subprocess.run([sys.executable, "-m", "build"], check=True)
            gw.info("Distribution package created in dist/")

            if twine:
                token = str(gw.resolve("[PYPI_API_TOKEN]", default="") or "").strip()
                if interactive_mode and not token:
                    token = _prompt_input("PyPI API token (leave blank to provide username/password): ")

                user = ""
                password = ""
                if not token:
                    try:
                        user = str(gw.resolve("[PYPI_USERNAME]")).strip()
                    except KeyError:
                        if interactive_mode:
                            user = _prompt_input("PyPI username: ")
                        else:
                            raise
                    try:
                        password = str(gw.resolve("[PYPI_PASSWORD]")).strip()
                    except KeyError:
                        if interactive_mode:
                            password = _prompt_input("PyPI password: ", secret=True)
                        else:
                            raise

                if not force:
                    releases = []
                    try:
                        import requests
                        url = f"https://pypi.org/pypi/{project_name}/json"
                        resp = requests.get(url, timeout=5)
                        if resp.ok:
                            data = resp.json()
                            releases = list(data.get("releases", {}).keys())
                        else:
                            gw.warning(f"Could not fetch releases for {project_name} from PyPI: HTTP {resp.status_code}")
                    except Exception as e:
                        gw.warning(f"Could not verify existing PyPI versions: {e}")
                    if new_version in releases:
                        gw.abort(
                            f"Version {new_version} is already on PyPI. "
                            "Use --force to override."
                        )

                gw.info("Validating distribution with twine check...")
                check_result = subprocess.run(
                    [sys.executable, "-m", "twine", "check", "dist/*"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True
                )
                if check_result.returncode != 0:
                    gw.error(
                        "PyPI README rendering check failed, aborting upload:\n"
                        f"{check_result.stdout}"
                    )
                    gw.info("Stashing release changes due to build failure...")
                    subprocess.run(
                        ["git", "stash", "--include-untracked", "-m", "gway-release-abort"],
                        check=False,
                    )
                    raise RuntimeError(
                        "Build aborted. README syntax errors detected.\n"
                        f"{check_result.stdout}"
                    )

                gw.info("Twine check passed.")

                token = token.strip()
                user = user.strip()
                password = password.strip()

                if token or (user and password):
                    gw.info("Uploading to PyPI...")
                    upload_command = [
                        sys.executable, "-m", "twine", "upload", "dist/*"
                    ]
                    if token:
                        upload_command += ["--username", "__token__", "--password", token]
                    else:
                        upload_command += ["--username", user, "--password", password]

                    subprocess.run(upload_command, check=True)
                    gw.info("Package uploaded to PyPI successfully.")
                else:
                    gw.warning(
                        "Twine upload skipped: missing PyPI token or username/password."
                    )

        if git:
            files_to_add = ["VERSION", "BUILD", "pyproject.toml", "CHANGELOG.rst"]
            if projects:
                files_to_add.append("README.rst")
            subprocess.run(["git", "add"] + files_to_add, check=True)
            commit_msg = f"PyPI Release v{version}" if twine else f"Release v{version}"
            subprocess.run(["git", "commit", "-m", commit_msg], check=True)
            subprocess.run(["git", "push"], check=True)
            gw.info(f"Committed and pushed: {commit_msg}")

        if tag:
            tag_name = f"v{version}"
            subprocess.run(["git", "tag", tag_name], check=True)
            subprocess.run(["git", "push", "origin", tag_name], check=True)
            gw.info(f"Created and pushed tag {tag_name}")

        if notify:
            gw.notify(f"Release v{version} build complete")

    try:
        _do_build()
    except SystemExit as exc:
        if exc.code not in (None, 0):
            _handle_failure(exc, traceback.format_exc())
        raise
    except Exception as exc:
        _handle_failure(exc, traceback.format_exc())
        raise


def auto_releaser(
    *,
    branch: str = "main",
    remote: str = "origin",
    poll_interval: float = 60.0,
    success_rest: float = 300.0,
    failure_rest: float = 60.0,
    retry_on_failure: bool = False,
    background: bool = False,
) -> dict[str, object] | None:
    """Continuously monitor the repository and trigger release builds.

    The helper polls ``remote/branch`` for new commits, fast-forwards the
    checkout and runs ``gway release build --all`` when changes are found.
    Successful releases pause for ``success_rest`` seconds (five minutes by
    default). Failures capture the git and release logs, raise a Windows toast
    notification and open Notepad with a detailed report so operators can act
    quickly. When ``background`` is true the loop is launched on a daemon
    thread so recipes can manage it via ``until``.
    """

    def _parse_bool(value: object) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        text = str(value).strip().lower()
        if text in {"", "0", "false", "off", "no", "n"}:
            return False
        if text in {"1", "true", "on", "yes", "y"}:
            return True
        raise ValueError(f"Cannot interpret {value!r} as a boolean flag")

    def _sleep(duration: float) -> None:
        if duration > 0:
            time.sleep(duration)

    def _run_command(command: list[str], name: str) -> subprocess.CompletedProcess[str]:
        gw.debug(f"[auto_releaser] Running {name}: {' '.join(command)}")
        return subprocess.run(command, capture_output=True, text=True)

    def _format_command(result: subprocess.CompletedProcess[str] | None) -> str:
        if result is None:
            return "Command not executed."
        args = result.args
        if isinstance(args, (list, tuple)):
            cmd_text = " ".join(str(part) for part in args)
        else:
            cmd_text = str(args)
        sections = [f"Command: {cmd_text}", f"Exit code: {result.returncode}"]
        stdout = (result.stdout or "").strip()
        stderr = (result.stderr or "").strip()
        if stdout:
            sections.append("STDOUT:\n" + stdout)
        if stderr:
            sections.append("STDERR:\n" + stderr)
        return "\n\n".join(sections)

    def _notify_failure(title: str, message: str) -> None:
        notifier = getattr(getattr(gw, "screen", None), "notify", None)
        if callable(notifier):
            try:
                notifier(message, title=title, timeout=30)
                return
            except Exception as exc:  # pragma: no cover - UI best effort
                gw.debug(f"[auto_releaser] screen.notify failed: {exc}")
        try:
            gw.notify(message, title=title, timeout=30)
        except Exception as exc:  # pragma: no cover - defensive logging
            gw.warning(f"[auto_releaser] Failed to send notification: {exc}")

    poll = max(1.0, float(poll_interval))
    success_delay = max(0.0, float(success_rest))
    failure_delay = max(0.0, float(failure_rest))
    retry_failed = _parse_bool(retry_on_failure)

    logs_dir = Path(gw.resource("logs", "auto_releaser", dir=True))
    system = platform.system()
    last_processed_remote: str | None = None

    def _loop() -> None:
        nonlocal last_processed_remote

        gw.info(
            "Starting auto releaser loop",
            extra={
                "remote": remote,
                "branch": branch,
                "poll_interval": poll,
                "success_rest": success_delay,
                "failure_rest": failure_delay,
                "retry_on_failure": retry_failed,
            },
        )

        try:
            while True:
                scan = auto_releaser_scan(
                    branch=branch,
                    remote=remote,
                    last_commit=last_processed_remote,
                )
                status = scan["status"]
                remote_ref = str(scan["remote_ref"])
                remote_commit = cast(str | None, scan.get("remote_commit"))
                head_commit = cast(str | None, scan.get("head_commit"))
                fetch_result = cast(
                    subprocess.CompletedProcess[str] | None,
                    scan.get("fetch_result"),
                )

                if status == "fetch-error":
                    timestamp = datetime.now()
                    report_path = logs_dir / f"failure_{timestamp:%Y%m%d_%H%M%S}.log"
                    report = textwrap.dedent(
                        f"""\
                        Auto releaser failure: git fetch
                        Timestamp: {timestamp.isoformat()}
                        Remote: {remote_ref}
                        Local HEAD: {head_commit or 'unknown'}

                        {_format_command(fetch_result)}
                        """
                    ).strip()
                    report_path.write_text(report + "\n", encoding="utf-8")
                    gw.error(f"[auto_releaser] git fetch failed. Report saved to {report_path}")
                    _notify_failure(
                        "Auto release failed",
                        f"git fetch failed for {remote_ref}. See {report_path}",
                    )
                    open_notepad(report_path)
                    _sleep(failure_delay)
                    continue

                if status == "missing-remote":
                    timestamp = datetime.now()
                    report_path = logs_dir / f"failure_{timestamp:%Y%m%d_%H%M%S}.log"
                    report = textwrap.dedent(
                        f"""\
                        Auto releaser failure: unknown remote commit
                        Timestamp: {timestamp.isoformat()}
                        Remote: {remote_ref}
                        Local HEAD: {head_commit or 'unknown'}

                        git fetch output:
                        {_format_command(fetch_result)}
                        """
                    ).strip()
                    report_path.write_text(report + "\n", encoding="utf-8")
                    gw.error(
                        f"[auto_releaser] Unable to resolve commit for {remote_ref}. Report saved to {report_path}"
                    )
                    _notify_failure(
                        "Auto release failed",
                        f"Cannot resolve {remote_ref}. See {report_path}",
                    )
                    open_notepad(report_path)
                    _sleep(failure_delay)
                    continue

                if status == "unchanged":
                    gw.debug(f"[auto_releaser] No changes detected on {remote_ref}. Sleeping {poll}s")
                    _sleep(poll)
                    continue

                gw.info(
                    f"New commit detected on {remote_ref}",
                    extra={"commit": remote_commit, "previous": last_processed_remote},
                )

                merge_result = _run_command(["git", "merge", "--ff-only", remote_ref], "git merge --ff-only")
                if merge_result.returncode != 0:
                    timestamp = datetime.now()
                    report_path = logs_dir / f"failure_{timestamp:%Y%m%d_%H%M%S}.log"
                    report_lines = [
                        "Auto releaser failure: git merge --ff-only",
                        f"Timestamp: {timestamp.isoformat()}",
                        f"Remote: {remote_ref}",
                        f"Remote commit: {remote_commit}",
                        f"Local HEAD: {head_commit or 'unknown'}",
                        "",
                        "git fetch output:",
                        _format_command(fetch_result),
                        "",
                        "git merge output:",
                        _format_command(merge_result),
                    ]
                    report_path.write_text("\n".join(report_lines) + "\n", encoding="utf-8")
                    gw.error(f"[auto_releaser] git merge failed. Report saved to {report_path}")
                    _notify_failure(
                        "Auto release failed",
                        f"git merge failed for {remote_ref}. See {report_path}",
                    )
                    open_notepad(report_path)
                    if not retry_failed:
                        last_processed_remote = remote_commit
                    _sleep(failure_delay)
                    continue

                head_commit = _git_rev_parse("HEAD")
                release_cmd = [sys.executable, "-m", "gway", "release", "build", "--all"]
                release_result = _run_command(release_cmd, "gway release build")

                if release_result.returncode == 0:
                    gw.info(
                        f"Release completed for {remote_ref}",
                        extra={"commit": remote_commit, "system": system},
                    )
                    last_processed_remote = remote_commit
                    _sleep(success_delay)
                    continue

                timestamp = datetime.now()
                report_path = logs_dir / f"failure_{timestamp:%Y%m%d_%H%M%S}.log"
                report_sections = [
                    "Auto releaser failure: release build",
                    f"Timestamp: {timestamp.isoformat()}",
                    f"Remote: {remote_ref}",
                    f"Remote commit: {remote_commit}",
                    f"Local HEAD: {head_commit or 'unknown'}",
                    "",
                    "git fetch output:",
                    _format_command(fetch_result),
                    "",
                    "git merge output:",
                    _format_command(merge_result),
                    "",
                    "release build output:",
                    _format_command(release_result),
                ]
                report_text = "\n".join(report_sections) + "\n"
                report_path.write_text(report_text, encoding="utf-8")
                short_commit = (remote_commit or "unknown")[:8]
                gw.error(
                    f"[auto_releaser] Release build failed for {remote_ref}@{short_commit}. Report saved to {report_path}"
                )
                _notify_failure(
                    "Auto release failed",
                    f"Release build failed for {remote_ref}@{short_commit}. See {report_path}",
                )
                open_notepad(report_path)
                if not retry_failed:
                    last_processed_remote = remote_commit
                _sleep(failure_delay)
        except KeyboardInterrupt:
            gw.info("Auto releaser loop interrupted by user")

    if background:
        thread_name = f"auto-releaser-{branch}"

        def _target() -> None:
            try:
                _loop()
            except Exception as exc:  # pragma: no cover - defensive logging
                gw.exception(exc)

        thread = threading.Thread(target=_target, name=thread_name, daemon=True)
        if hasattr(gw, "_async_threads"):
            gw._async_threads.append(thread)
        thread.start()
        return {
            "status": "started",
            "thread": thread.name,
            "remote": remote,
            "branch": branch,
            "poll_interval": poll,
            "success_rest": success_delay,
            "failure_rest": failure_delay,
            "retry_on_failure": retry_failed,
        }

    _loop()
    return {
        "status": "stopped",
        "remote": remote,
        "branch": branch,
    }


def build_help_db():
    """Compatibility wrapper that delegates to :mod:`help_db`."""
    return gw.help_db.build(update=True)




def loc(*paths):
    """
    Counts Python lines of code in the given directories, ignoring hidden files and directories.
    Defaults to everything in the current GWAY release.
    """
    file_counts = {}
    total_lines = 0

    paths = paths if paths else ("projects", "gway", "tests")
    for base_path in paths:
        base_dir = gw.resource(base_path)
        for root, dirs, files in os.walk(base_dir):
            # Modify dirs in-place to skip hidden directories
            dirs[:] = [d for d in dirs if not d.startswith('.') and not d.startswith('_')]
            for file in files:
                if file.startswith('.') or file.startswith('_'):
                    continue
                if file.endswith('.py'):
                    file_path = os.path.join(root, file)
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            lines = f.readlines()
                            line_count = len(lines)
                            file_counts[file_path] = line_count
                            total_lines += line_count
                    except (UnicodeDecodeError, FileNotFoundError):
                        # Skip files that can't be read
                        continue

    file_counts['total'] = total_lines
    return file_counts


def benchmark_sigils(iterations: int = 10000) -> float:
    """Benchmark Sigil resolution performance."""
    from time import perf_counter
    from gway.sigils import Sigil

    ctx = {
        "name": "Bench",
        "num": 42,
        "info": {"x": 1, "y": 2},
    }
    samples = [
        Sigil("[name]"),
        Sigil("Value [num]"),
        Sigil("[info.x]"),
        Sigil("[info]")
    ]

    start = perf_counter()
    for _ in range(iterations):
        for s in samples:
            _ = s % ctx
    elapsed = perf_counter() - start
    gw.info(
        f"Resolved {iterations * len(samples)} sigils in {elapsed:.4f}s"
    )
    return elapsed


def create_shortcut(
    name="Launch GWAY",
    target=r"gway.bat",
    hotkey="Ctrl+Alt+G",
    output_dir=None,
    icon=None,
):
    from win32com.client import Dispatch

    # Resolve paths
    base_dir = Path(__file__).resolve().parent
    target_path = base_dir / target
    output_dir = output_dir or Path.home() / "Desktop"
    shortcut_path = Path(output_dir) / f"{name}.lnk"

    shell = Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(str(shortcut_path))
    shortcut.TargetPath = str(target_path)
    shortcut.WorkingDirectory = str(base_dir)
    shortcut.WindowStyle = 1  # Normal window
    if icon:
        shortcut.IconLocation = str(icon)
    shortcut.Hotkey = hotkey  # e.g. Ctrl+Alt+G
    shortcut.Description = "Launch GWAY from anywhere"
    shortcut.Save()

    print(f"Shortcut created at: {shortcut_path}")


def commit(length: int = 6) -> str:
    """Return the current git commit hash via :mod:`hub` utilities."""
    return gw.hub.commit(length)


def get_build(length: int = 6) -> str:
    """Return the build hash stored in the BUILD file via :mod:`hub`."""
    return gw.hub.get_build(length)


def changes(*, files=None, staged=False, context=3, max_bytes=200_000, clip=False):
    """Return a unified diff using :mod:`hub` utilities."""
    return gw.hub.changes(files=files, staged=staged, context=context, max_bytes=max_bytes, clip=clip)


def build_requirements(func):
    """Generate a requirements file for ``func`` and its callees."""

    if isinstance(func, str):
        module_name, attr = func.rsplit(".", 1)
        mod = __import__(module_name, fromlist=[attr])
        func = getattr(mod, attr)

    visited = set()
    modules = set()

    def is_stdlib(name: str) -> bool:
        try:
            spec = importlib.util.find_spec(name)
        except ModuleNotFoundError:
            return False
        if not spec or not spec.origin:
            return True
        path = spec.origin or ""
        return "site-packages" not in path and "dist-packages" not in path

    def gather(f):
        if not callable(f) or f in visited:
            return
        visited.add(f)
        try:
            source = inspect.getsource(f)
        except Exception:
            return
        tree = ast.parse(source)
        globals_ = getattr(f, "__globals__", {})
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[0]
                    if not is_stdlib(name):
                        modules.add(name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    name = node.module.split(".")[0]
                    if not is_stdlib(name):
                        modules.add(name)
            elif isinstance(node, ast.Call):
                target = None
                if isinstance(node.func, ast.Name):
                    target = globals_.get(node.func.id)
                elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    base = globals_.get(node.func.value.id)
                    if base is not None:
                        target = getattr(base, node.func.attr, None)
                if inspect.isfunction(target):
                    gather(target)
                elif inspect.ismodule(target):
                    name = target.__name__.split(".")[0]
                    if not is_stdlib(name):
                        modules.add(name)

    gather(func)

    qualname = getattr(func, "__qualname__", getattr(func, "__name__", "func"))
    dest = Path("work") / "release" / qualname.replace(".", "_")
    dest.mkdir(parents=True, exist_ok=True)
    req_file = dest / "requirements.txt"
    req_file.write_text("\n".join(sorted(modules)) + "\n", encoding="utf-8")
    gw.info(f"Wrote requirements to {req_file}")
    return req_file


def _last_changelog_build():
    path = Path("CHANGELOG.rst")
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("#"):
            continue
        if "[build" in line:
            try:
                return line.split("[build", 1)[1].split("]", 1)[0].strip()
            except Exception:
                return None
    return None


def _ensure_changelog() -> str:
    """Return the changelog text ensuring base headers and an Unreleased section."""
    base_header = "Changelog\n=========\n\n"
    path = Path("CHANGELOG.rst")
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if not text.startswith("Changelog"):
        text = base_header + text
    if "Unreleased" not in text:
        text = text[: len(base_header)] + "Unreleased\n----------\n\n" + text[len(base_header):]
    return text


def _pop_unreleased(text: str) -> tuple[str, str]:
    """Return (body, new_text) removing the Unreleased section."""
    lines = text.splitlines()
    try:
        idx = lines.index("Unreleased")
    except ValueError:
        return "", text

    body = []
    i = idx + 2  # Skip underline
    while i < len(lines) and lines[i].startswith("- "):
        body.append(lines[i])
        i += 1
    if i < len(lines) and lines[i] == "":
        i += 1
    new_lines = lines[:idx] + lines[i:]
    return "\n".join(body), "\n".join(new_lines) + ("\n" if text.endswith("\n") else "")


def add_note(message: str | None = None) -> None:
    """Append a bullet to the Unreleased section of CHANGELOG.rst."""
    import subprocess

    if message is None:
        try:
            proc = subprocess.run(
                ["git", "log", "-1", "--pretty=%h %s", "--no-merges"],
                capture_output=True,
                text=True,
                check=True,
            )
            message = proc.stdout.strip()
            if message.startswith("Merge"):
                message = ""
        except Exception:
            message = ""

    if not message:
        gw.warning("No changelog entry provided and git log failed.")
        return

    path = Path("CHANGELOG.rst")
    text = _ensure_changelog()
    lines = text.splitlines()
    try:
        idx = lines.index("Unreleased")
    except ValueError:
        idx = None
    if idx is None:
        lines.insert(2, "Unreleased")
        lines.insert(3, "-" * len("Unreleased"))
        lines.insert(4, "")
        idx = 2
    insert = idx + 2
    lines.insert(insert, f"- {message}")
    lines.insert(insert + 1, "")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_changelog(version: str, build_hash: str, prev_build: str | None = None) -> None:
    """Promote the Unreleased section to a new version entry."""
    import subprocess

    text = _ensure_changelog()

    unreleased_body, text = _pop_unreleased(text)

    if not unreleased_body:
        prev_build = prev_build or _last_changelog_build()
        log_range = f"{prev_build}..HEAD" if prev_build else "HEAD"
        commits = []
        try:
            proc = subprocess.run(
                ["git", "log", "--pretty=%h %s", "--no-merges", log_range],
                capture_output=True,
                text=True,
                check=True,
            )
            commits = [
                f"- {line.strip()}"
                for line in proc.stdout.splitlines()
                if line.strip() and not line.strip().startswith("Merge")
            ]
        except subprocess.CalledProcessError:
            try:
                proc = subprocess.run(
                    ["git", "log", "-1", "--pretty=%h %s", "--no-merges"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                commits = [
                    f"- {line.strip()}"
                    for line in proc.stdout.splitlines()
                    if line.strip() and not line.strip().startswith("Merge")
                ]
            except Exception:
                commits = []
        except Exception:
            commits = []
        unreleased_body = "\n".join(commits)

    header = f"{version} [build {build_hash}]"
    underline = "-" * len(header)
    entry = "\n".join([header, underline, "", unreleased_body, ""]).rstrip() + "\n\n"

    base_header = "Changelog\n=========\n\n"
    remaining = text[len(base_header):]
    new_text = base_header + "Unreleased\n----------\n\n" + entry + remaining

    Path("CHANGELOG.rst").write_text(new_text, encoding="utf-8")


def update_readme_links(readme_path: str | Path = "README.rst") -> None:
    """Rewrite project README links with the resolved DOMAIN.

    Web features have been removed, so this now simply validates the DOMAIN
    setting without altering the README content.
    """
    domain = gw.resolve("[DOMAIN]", "")
    if not domain:
        gw.warning("DOMAIN not configured, skipping README link update.")
        return
    path = Path(readme_path)
    text = path.read_text(encoding="utf-8")
    path.write_text(text, encoding="utf-8")
    gw.info(f"Checked README links using domain {domain}")


def view_changelog():
    """Render the changelog, hiding an empty ``Unreleased`` section."""
    from docutils.core import publish_parts

    text = _ensure_changelog()
    unreleased_body, trimmed = _pop_unreleased(text)
    if not unreleased_body.strip():
        text = trimmed

    return publish_parts(source=text, writer_name="html")["html_body"]


# === Background Test Cache ===
_TEST_CACHE = {
    "running": False,
    "progress": 0.0,
    "total": 0,
    "tests": [],
    "coverage": {},
}


def _update_progress(result, total):
    if total:
        _TEST_CACHE["progress"] = result / total * 100.0


def _run_tests():
    _TEST_CACHE.update({
        "running": True,
        "progress": 0.0,
        "tests": [],
        "coverage": {},
    })

    suite = unittest.defaultTestLoader.discover("tests")
    total = suite.countTestCases()
    _TEST_CACHE["total"] = total

    cov = Coverage() if Coverage else None
    if cov:
        cov.start()

    class CacheResult(unittest.TextTestResult):
        def startTest(self, test):
            super().startTest(test)
            self._start_time = time.perf_counter()
            _TEST_CACHE["tests"].append({
                "name": str(test),
                "status": "?",
                "time": 0.0,
            })

        def addSuccess(self, test):
            for t in _TEST_CACHE["tests"]:
                if t["name"] == str(test):
                    t["status"] = "\u2713"  # check mark
                    break
            super().addSuccess(test)

        def addFailure(self, test, err):
            for t in _TEST_CACHE["tests"]:
                if t["name"] == str(test):
                    t["status"] = "\u2717"  # cross mark
                    break
            super().addFailure(test, err)

        def addError(self, test, err):
            for t in _TEST_CACHE["tests"]:
                if t["name"] == str(test):
                    t["status"] = "\u2717"
                    break
            super().addError(test, err)

        def stopTest(self, test):
            elapsed = time.perf_counter() - getattr(self, "_start_time", time.perf_counter())
            for t in _TEST_CACHE["tests"]:
                if t["name"] == str(test):
                    t["time"] = elapsed
                    break
            _update_progress(self.testsRun, total)
            super().stopTest(test)

    runner = unittest.TextTestRunner(verbosity=2, resultclass=CacheResult)
    runner.run(suite)

    if cov:
        cov.stop()
        data = cov.get_data()
        built_run = built_total = 0
        proj_totals = {}
        for f in data.measured_files():
            if not f.endswith(".py"):
                continue
            try:
                filename, stmts, exc, miss, _ = cov.analysis2(f)
            except Exception:
                continue
            total_lines = len(stmts)
            run_lines = total_lines - len(miss)
            rel = os.path.relpath(f)
            if rel.startswith("projects" + os.sep):
                parts = rel.split(os.sep)
                key = "/".join(parts[:2]) if len(parts) > 1 else parts[0]
                run, tot = proj_totals.get(key, (0, 0))
                proj_totals[key] = (run + run_lines, tot + total_lines)
            else:
                built_run += run_lines
                built_total += total_lines

        proj_cov = {k: (r / t * 100 if t else 100.0) for k, (r, t) in proj_totals.items()}
        proj_total_run = sum(r for r, _ in proj_totals.values())
        proj_total_lines = sum(t for _, t in proj_totals.values())
        _TEST_CACHE["coverage"] = {
            "builtins_total": built_run / built_total * 100 if built_total else 100.0,
            "projects": proj_cov,
            "projects_total": proj_total_run / proj_total_lines * 100 if proj_total_lines else 100.0,
        }

    _TEST_CACHE["running"] = False


def setup_app(*, app=None, **_):
    gw.update_modes(timed=True)
    if not _TEST_CACHE.get("running"):
        thread = threading.Thread(target=_run_tests, daemon=True)
        thread.start()
    return app


def render_test_log(lines: int = 50):
    try:
        path = gw.resource("logs", "test.log")
        with open(path, "r", encoding="utf-8") as lf:
            tail = lf.readlines()[-lines:]
    except Exception:
        tail = ["(log unavailable)"]
    tail.reverse()
    esc = html.escape
    return "<pre>" + "".join(esc(t) for t in tail) + "</pre>"


if __name__ == "__main__":
    build()
