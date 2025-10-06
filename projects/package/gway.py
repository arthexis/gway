"""Gateway-specific package upgrade helpers."""

from __future__ import annotations

import subprocess

from gway import gw

from . import (
    CycleState,
    UpgradeConfig,
    current_release as _current_release,
    install as _install,
    log_cycle as _log_cycle,
    log_upgrade as _log_upgrade,
    notify_upgrade as _notify_upgrade,
)

__all__ = [
    "LOG_NAME",
    "CONFIG",
    "CycleState",
    "log_cycle",
    "install",
    "log_upgrade",
    "current_release",
    "notify_upgrade",
    "install_builtin",
    "upgrade_builtin",
]

LOG_NAME = "auto_upgrade.log"


def _broadcast(message: str) -> None:
    """Send *message* to logged-in users via ``wall`` when available."""

    try:
        subprocess.run(
            ["wall", message],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        gw.debug("wall binary not available; skipping broadcast")
    except Exception as exc:  # pragma: no cover - best effort notification
        gw.debug(f"Failed to broadcast upgrade message: {exc}")


def _release_lookup(length: int) -> str | None:
    try:
        return gw.hub.get_build(length=length)
    except Exception as exc:  # pragma: no cover - best effort helper
        gw.debug(f"Unable to determine build identifier: {exc}")
        return None


def _normalise_release(release: str | None) -> str | None:
    if not release:
        return None
    return release.lstrip("rR").upper()


CONFIG = UpgradeConfig(
    package="gway",
    log_name=LOG_NAME,
    context_prefix="auto_upgrade",
    install_mode="pip",
    env_latest_var="AUTO_UPGRADE_LATEST",
    broadcast_template="gway upgraded to {version}",
    notify_title_template="gway v{version} r{release}",
    notify_time_format="%Y%m%d %H:%M",
    release_length=6,
    release_lookup=_release_lookup,
    release_normalizer=_normalise_release,
    fallback_release="000000",
)


def log_cycle(*, latest: bool | str | None = None, log_name: str = LOG_NAME) -> CycleState:
    """Record a log entry for the start of a new Gateway upgrade check."""

    return _log_cycle(CONFIG, latest=latest, log_name=log_name)


def install(*, latest: bool | str | None = None) -> int:
    """Install or upgrade ``gway`` using the install builtin."""

    return _install(CONFIG, latest=latest)


def log_upgrade(
    *,
    version: str | None = None,
    latest: bool | str | None = None,
    log_name: str = LOG_NAME,
    notify: bool = True,
    broadcaster=None,
) -> dict:
    """Record the outcome of an applied upgrade and optionally notify users."""

    active = broadcaster if broadcaster is not None else (_broadcast if notify else None)
    return _log_upgrade(
        CONFIG,
        version=version,
        latest=latest,
        log_name=log_name,
        notify=notify,
        broadcaster=active,
    )


def current_release(length: int = 6) -> str | None:
    """Return the current build identifier if available."""

    return _current_release(CONFIG, length=length)


def notify_upgrade(
    *,
    version: str | None = None,
    release: str | None = None,
    latest: bool | str | None = None,
    timestamp=None,
    timeout: int = 20,
) -> dict:
    """Display a toast/LCD message summarising a successful upgrade."""

    return _notify_upgrade(
        CONFIG,
        version=version,
        release=release,
        latest=latest,
        timestamp=timestamp,
        timeout=timeout,
    )


def install_builtin(
    recipe: str | None = None,
    *recipe_args,
    repair: bool = False,
    remove: bool = False,
    bin: bool = False,
    force: bool = False,
    debug: bool = False,
    root: bool = False,
    mode: str = "script",
    latest: bool | str | None = None,
    quiet: bool | str | None = True,
) -> int:
    """Run ``install.sh``/``install.bat`` or upgrade packages via ``pip``."""

    from gway import gw

    import os
    import shlex
    import subprocess
    import sys
    from threading import Thread

    def _bool_from(value) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        text = str(value).strip().lower()
        if not text:
            return False
        return text in {"1", "true", "yes", "on", "force"}

    normalized_mode = str(mode or "script").strip().lower() or "script"
    if normalized_mode not in {"script", "pip"}:
        raise ValueError(f"Unsupported install mode: {mode!r}")

    if normalized_mode == "pip":
        packages: list[str] = []
        if recipe is not None:
            recipe_text = str(recipe).strip()
            if recipe_text:
                packages.append(recipe_text)
        for value in recipe_args:
            value_text = str(value).strip()
            if value_text:
                packages.append(value_text)
        if not packages:
            packages.append("gway")

        quiet_requested = _bool_from(quiet)
        if debug:
            quiet_requested = False

        def _latest_requested(explicit: bool | str | None = None) -> bool:
            if explicit is not None:
                return _bool_from(explicit)

            for key in ("auto_upgrade_latest", "latest", "LATEST"):
                if key in gw.context:
                    return _bool_from(gw.context[key])

            env_flag = os.environ.get("AUTO_UPGRADE_LATEST")
            if env_flag is not None:
                return _bool_from(env_flag)

            return "--latest" in sys.argv

        latest_requested = _latest_requested(latest)

        if any([repair, remove, bin, root]):
            raise ValueError(
                "Options --repair, --remove, --bin and --root cannot be used with pip mode."
            )

        python_exec = sys.executable or "python3"
        pip_cmd: list[str] = [python_exec, "-m", "pip", "install"]
        if quiet_requested:
            pip_cmd.append("--quiet")
        pip_cmd.append("--upgrade")
        if debug:
            pip_cmd.append("--verbose")
        if force or latest_requested:
            pip_cmd.append("--force-reinstall")
        pip_cmd.extend(packages)

        pretty_cmd = " ".join(shlex.quote(part) for part in pip_cmd)
        gw.info(f"install (pip): running {pretty_cmd}")

        result = subprocess.run(pip_cmd, check=False)
        if result.returncode != 0:
            gw.error(f"pip install failed with exit code {result.returncode}")
            raise subprocess.CalledProcessError(result.returncode, pip_cmd)

        return result.returncode

    if repair and (remove or bin):
        raise ValueError(
            "Options --repair, --remove and --bin are mutually exclusive. "
            "Combine --remove with --bin to uninstall that integration."
        )
    if not remove and sum(bool(flag) for flag in (repair, bin)) > 1:
        raise ValueError(
            "Options --repair, --remove and --bin are mutually exclusive. "
            "Combine --remove with --bin to uninstall that integration."
        )

    if recipe_args and not recipe:
        raise ValueError("Recipe arguments require a recipe name or path")

    if repair and recipe:
        raise ValueError("--repair cannot be combined with a recipe argument")
    if bin and recipe and not remove:
        raise ValueError("--bin cannot be combined with a recipe argument")
    if remove and not recipe and not bin:
        raise ValueError("--remove requires a recipe name or path")
    if root and (remove or repair or bin or not recipe):
        raise ValueError("--root can only be used when installing a recipe service")

    script_name = "install.sh"
    runner: list[str] = ["bash"]

    if os.name == "nt":
        script_name = "install.bat"
        runner = ["cmd", "/c"]

    script = gw.resource(script_name, check=True)

    cmd = [*runner, os.fspath(script)]
    if repair:
        cmd.append("--repair")
    if bin:
        cmd.append("--bin")
    if remove:
        cmd.append("--remove")
    if force:
        cmd.append("--force")
    if debug:
        cmd.append("--debug")
    if root:
        cmd.append("--root")
    if recipe:
        cmd.append(recipe)
    if recipe_args:
        cmd.extend(recipe_args)

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
    for thread in threads:
        thread.start()
    process.wait()
    for thread in threads:
        thread.join()
    return process.returncode


def upgrade_builtin(*args, _temp_env=None):
    """Run ``upgrade.sh`` with the given parameters."""

    from gway import gw

    import os
    import subprocess
    import sys
    from threading import Thread

    safe_mode = False
    forwarded_args = []
    request_full_tests = False
    skip_tests = False
    allowed_flags = {"--force", "--latest", "--test", "--no-test", "-h", "--help"}
    for arg in args:
        if arg == "--safe":
            safe_mode = True
            continue
        if arg not in allowed_flags:
            raise ValueError(f"Unrecognized upgrade option: {arg}")
        forwarded_args.append(arg)
        if arg == "--test":
            request_full_tests = True
        elif arg == "--no-test":
            skip_tests = True

    if request_full_tests and skip_tests:
        raise ValueError("--test and --no-test cannot be used together")

    help_requested = any(arg in {"-h", "--help"} for arg in forwarded_args)

    if safe_mode:
        if skip_tests:
            gw.info("Skipping safe upgrade check because --no-test was provided.")
        elif help_requested:
            gw.info("Skipping safe upgrade check because help was requested.")
        else:
            mode_label = "full test suite" if request_full_tests else "smoke tests"
            gw.info(
                f"Running safe upgrade check in temporary environment ({mode_label})..."
            )
            test_args = ["gway", "test"]
            if not request_full_tests:
                test_args.extend(["--filter", "smoke"])
            test_args.extend(["--on-failure", "abort"])
            temp_env_runner = _temp_env or gw.temp_env
            try:
                temp_env_runner(*test_args, pip_args="--quiet")
            except subprocess.CalledProcessError as exc:
                gw.error("Safe upgrade check failed; aborting upgrade.")
                return exc.returncode or 1
            except Exception as exc:  # pragma: no cover - defensive: log unexpected failures
                gw.error(f"Safe upgrade check encountered an unexpected error: {exc}")
                try:
                    gw.exception(exc)
                except Exception:
                    pass
                return 1

    script = gw.resource("upgrade.sh", check=True)
    script_path = os.fspath(script)
    if os.name == "nt":  # pragma: no cover - exercised via unit test patching
        script_path = script.as_posix()
    cmd = ["bash", script_path, *forwarded_args]

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
    for thread in threads:
        thread.start()
    process.wait()
    for thread in threads:
        thread.join()
    return process.returncode

