from __future__ import annotations

import getpass
import os
import re
import stat
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import pwd
except ImportError:  # pragma: no cover - unavailable on Windows
    pwd = None  # type: ignore[assignment]

from ..log_consumers import consumer_environment_file
from ..project import Project
from ..runner import Runner
from .manifest import ServiceError, _strings

_UNIT_NAME = re.compile(r"^[A-Za-z0-9_.@-]+$")


@dataclass(frozen=True)
class _WritablePathPlan:
    path: Path
    root: Path
    account: str
    uid: int
    gid: int


def _service_user(config: dict[str, Any], override: str | None) -> str:
    configured = config.get("user")
    if configured is not None and not isinstance(configured, str):
        raise ServiceError("service user must be a string")
    value = override or configured or os.environ.get("SUDO_USER") or getpass.getuser()
    value = value.strip()
    if not value or any(character.isspace() for character in value):
        raise ServiceError("service user must be a non-empty account name")
    return value


def _unit_arg(value: str | Path) -> str:
    text = str(value)
    if "\n" in text or "\r" in text:
        raise ServiceError("systemd arguments must not contain newlines")
    text = text.replace("%", "%%").replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _unit_path(value: str | Path, field: str) -> str:
    text = str(value)
    if "\n" in text or "\r" in text:
        raise ServiceError(f"{field} must not contain newlines")
    if not Path(text).is_absolute():
        raise ServiceError(f"{field} must expand to an absolute path")
    return text


def _unit_reference(value: str, field: str) -> str:
    if not value or any(character.isspace() for character in value):
        raise ServiceError(f"{field} must contain systemd unit names without whitespace")
    return value


def _project_python(project: Project) -> str:
    environment = project.environment
    if environment is None and project.install_layout is not None:
        environment = project.install_layout.environment
    if environment is None:
        return sys.executable
    return str(Runner.environment_python(environment))


def _expand(value: str, project: Project) -> str:
    return value.replace("{python}", _project_python(project)).replace(
        "{project}", str(project.path)
    )


def _managed_root(project: Project) -> Path:
    if project.install_layout is not None:
        return project.install_layout.root.resolve()
    return project.path.resolve()


def _writable_paths(config: dict[str, Any], project: Project, section: str) -> list[Path]:
    values = _strings(config.get("writable_paths"), "writable_paths", section)
    if not values:
        return []
    root = _managed_root(project)
    paths: list[Path] = []
    for value in values:
        expanded = Path(_expand(value, project)).expanduser()
        if not expanded.is_absolute():
            raise ServiceError(f"[{section}].writable_paths entries must expand to absolute paths")
        # Keep the target lexical after normalizing `..`: resolving here would
        # follow a mutable symlink before the race-safe descriptor traversal.
        target = Path(os.path.abspath(expanded))
        if target == root or root not in target.parents:
            raise ServiceError(
                f"[{section}].writable_paths entries must stay below managed root {root}"
            )
        paths.append(target)
    return paths


def _directory_flags() -> int:
    flags = os.O_RDONLY
    flags |= getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    return flags


def _open_directory(name: str | Path, *, dir_fd: int | None = None) -> int:
    try:
        return os.open(name, _directory_flags(), dir_fd=dir_fd)
    except OSError as exc:
        raise ServiceError(f"writable path component is not a safe directory: {name}") from exc


def _chown_tree_fd(directory_fd: int, uid: int, gid: int) -> None:
    """Recursively chown through pinned directory descriptors without following links."""
    os.fchown(directory_fd, uid, gid)
    try:
        names = os.listdir(directory_fd)
    except OSError as exc:
        raise ServiceError("cannot enumerate managed writable path") from exc
    for name in names:
        try:
            metadata = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as exc:
            raise ServiceError(f"cannot inspect managed writable path entry: {name}") from exc
        if stat.S_ISDIR(metadata.st_mode):
            child_fd = _open_directory(name, dir_fd=directory_fd)
            try:
                _chown_tree_fd(child_fd, uid, gid)
            finally:
                os.close(child_fd)
            continue
        try:
            os.chown(name, uid, gid, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as exc:
            raise ServiceError(f"cannot assign managed writable path entry: {name}") from exc


def _service_gids(plan: _WritablePathPlan) -> set[int]:
    gids = {plan.gid}
    getgrouplist = getattr(os, "getgrouplist", None)
    if getgrouplist is None:
        return gids
    try:
        gids.update(getgrouplist(plan.account, plan.gid))
    except OSError:
        pass
    return gids


def _mode_allows(metadata: os.stat_result, uid: int, gids: set[int], required: int) -> bool:
    if uid == 0:
        return True
    mode = stat.S_IMODE(metadata.st_mode)
    if metadata.st_uid == uid:
        granted = (mode >> 6) & 0o7
    elif metadata.st_gid in gids:
        granted = (mode >> 3) & 0o7
    else:
        granted = mode & 0o7
    return granted & required == required


def _validate_writable_path_access(plan: _WritablePathPlan) -> None:
    """Confirm the configured service account can traverse and write its runtime path."""
    try:
        relative = plan.path.relative_to(plan.root)
    except ValueError as exc:
        raise ServiceError(f"writable path escapes managed root: {plan.path}") from exc
    gids = _service_gids(plan)
    root_fd = _open_directory(plan.root)
    current_fd = root_fd
    try:
        if not _mode_allows(os.fstat(root_fd), plan.uid, gids, 0o1):
            raise ServiceError(
                f"service user {plan.account!r} cannot traverse managed root {plan.root}"
            )
        for index, component in enumerate(relative.parts):
            child_fd = _open_directory(component, dir_fd=current_fd)
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = child_fd
            required = 0o3 if index == len(relative.parts) - 1 else 0o1
            if not _mode_allows(os.fstat(current_fd), plan.uid, gids, required):
                action = "write" if required == 0o3 else "traverse"
                raise ServiceError(
                    f"service user {plan.account!r} cannot {action} managed runtime path {plan.path}"
                )
    finally:
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)


def _prepare_writable_path(plan: _WritablePathPlan) -> None:
    """Create, own, and validate one managed path using no-follow descriptor traversal."""
    try:
        relative = plan.path.relative_to(plan.root)
    except ValueError as exc:  # defensive; manifests are validated earlier
        raise ServiceError(f"writable path escapes managed root: {plan.path}") from exc
    if not relative.parts:
        raise ServiceError("managed root itself cannot be declared writable")

    root_fd = _open_directory(plan.root)
    current_fd = root_fd
    try:
        for component in relative.parts:
            try:
                child_fd = os.open(component, _directory_flags(), dir_fd=current_fd)
                created = False
            except FileNotFoundError:
                try:
                    os.mkdir(component, mode=0o755, dir_fd=current_fd)
                    child_fd = os.open(component, _directory_flags(), dir_fd=current_fd)
                    created = True
                except OSError as exc:
                    raise ServiceError(
                        f"cannot create managed writable path component: {component}"
                    ) from exc
            except OSError as exc:
                raise ServiceError(
                    f"writable path component is not a safe directory: {component}"
                ) from exc

            if created:
                # mkdir honors umask; normalize newly created ancestors so the
                # service account can traverse them even under a restrictive umask.
                os.fchmod(child_fd, 0o755)
                os.fchown(child_fd, plan.uid, plan.gid)
            if current_fd != root_fd:
                os.close(current_fd)
            current_fd = child_fd

        # Existing lock/state/log/cache/run trees may have been created by an
        # earlier privileged invocation. Re-home the full runtime tree before
        # the service starts so new locks are subsequently created by its user.
        _chown_tree_fd(current_fd, plan.uid, plan.gid)
    finally:
        if current_fd != root_fd:
            os.close(current_fd)
        os.close(root_fd)

    _validate_writable_path_access(plan)


def _paths_overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def _validate_writable_plans(plans: list[_WritablePathPlan]) -> list[_WritablePathPlan]:
    """Reject incompatible overlapping ownership claims and deduplicate exact claims."""
    accepted: list[_WritablePathPlan] = []
    for plan in plans:
        duplicate = False
        for prior in accepted:
            if not _paths_overlap(plan.path, prior.path):
                continue
            if (plan.uid, plan.gid) != (prior.uid, prior.gid):
                raise ServiceError(
                    "conflicting service owners for overlapping writable paths: "
                    f"{prior.path} ({prior.account}) and {plan.path} ({plan.account})"
                )
            if plan.path == prior.path:
                duplicate = True
        if not duplicate:
            accepted.append(plan)
    return sorted(accepted, key=lambda item: len(item.path.parts))


def _systemctl(*arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    if arguments and arguments[0] in {"start", "restart"} and len(arguments) > 1:
        subprocess.run(
            ["systemctl", "reset-failed", *arguments[1:]],
            check=False,
            text=True,
            capture_output=True,
        )
    return subprocess.run(["systemctl", *arguments], check=check, text=True, capture_output=True)


class _ServiceUnit:
    def __init__(
        self,
        project: Project,
        key: str,
        config: dict[str, Any],
        *,
        legacy: bool,
        unit_directory: Path,
        profile: str | None = None,
    ) -> None:
        self.project = project
        self.key = key
        self.config = config
        self.legacy = legacy
        self.unit_directory = unit_directory
        self.profile = profile
        self.unit_name = self._unit_name()
        self.unit_path = unit_directory / self.unit_name

    @property
    def section(self) -> str:
        return "service" if self.legacy else f"services.{self.key}"

    def _unit_name(self) -> str:
        default = f"gway-{self.project.name}"
        if not self.legacy:
            default = f"{default}-{self.key}"
        value = self.config.get("name", default)
        if not isinstance(value, str) or not value or not _UNIT_NAME.fullmatch(value):
            raise ServiceError("service name must be a safe systemd unit name")
        return value if value.endswith(".service") else f"{value}.service"

    def writable_paths(self) -> list[Path]:
        return _writable_paths(self.config, self.project, self.section)

    def writable_path_plans(self, *, user: str | None = None) -> list[_WritablePathPlan]:
        paths = self.writable_paths()
        if not paths:
            return []
        account = _service_user(self.config, user)
        if pwd is None:
            raise ServiceError("managed writable paths require POSIX account lookup")
        try:
            identity = pwd.getpwnam(account)
        except KeyError as exc:
            raise ServiceError(f"service user does not exist: {account}") from exc
        root = _managed_root(self.project)
        return [
            _WritablePathPlan(
                path=path,
                root=root,
                account=account,
                uid=identity.pw_uid,
                gid=identity.pw_gid,
            )
            for path in paths
        ]

    def prepare_writable_paths(self, *, user: str | None = None) -> None:
        for plan in _validate_writable_plans(self.writable_path_plans(user=user)):
            _prepare_writable_path(plan)

    def render(self, *, user: str | None = None) -> str:
        section = self.section
        command = _strings(self.config.get("command"), "command", section)
        if not command:
            raise ServiceError(f"[{section}].command must contain at least one argument")
        command = [_expand(argument, self.project) for argument in command]
        self.writable_paths()
        default_description = (
            f"GWAY {self.project.name} service"
            if self.legacy
            else f"GWAY {self.project.name} {self.key} service"
        )
        description = self.config.get("description", default_description)
        if not isinstance(description, str) or not description.strip():
            raise ServiceError(f"[{section}].description must be a non-empty string")
        if "\n" in description or "\r" in description:
            raise ServiceError(f"[{section}].description must not contain newlines")
        wants = _strings(self.config.get("wants", ["network-online.target"]), "wants", section)
        after = _strings(self.config.get("after", ["network-online.target"]), "after", section)
        requires = _strings(self.config.get("requires"), "requires", section)
        on_failure = [
            _unit_reference(value, f"[{section}].on_failure")
            for value in _strings(self.config.get("on_failure"), "on_failure", section)
        ]
        restart = self.config.get("restart", "on-failure")
        restart_sec = self.config.get("restart_sec", 5)
        timeout_stop_sec = self.config.get("timeout_stop_sec", 20)
        start_limit_interval_sec = self.config.get("start_limit_interval_sec", "15min")
        start_limit_burst = self.config.get("start_limit_burst", 3)
        if not isinstance(restart, str) or not restart:
            raise ServiceError(f"[{section}].restart must be a non-empty string")
        if not isinstance(restart_sec, (int, float)) or restart_sec < 0:
            raise ServiceError(f"[{section}].restart_sec must be a non-negative number")
        if not isinstance(timeout_stop_sec, (int, float)) or timeout_stop_sec < 0:
            raise ServiceError(f"[{section}].timeout_stop_sec must be a non-negative number")
        if (
            isinstance(start_limit_interval_sec, bool)
            or not isinstance(start_limit_interval_sec, (str, int, float))
            or not str(start_limit_interval_sec).strip()
        ):
            raise ServiceError(
                f"[{section}].start_limit_interval_sec must be a non-empty systemd time span"
            )
        if (
            isinstance(start_limit_burst, bool)
            or not isinstance(start_limit_burst, int)
            or start_limit_burst < 1
        ):
            raise ServiceError(f"[{section}].start_limit_burst must be a positive integer")
        configured_environment = self.config.get("environment", {"PYTHONUNBUFFERED": "1"})
        valid_environment = isinstance(configured_environment, dict) and all(
            isinstance(key, str) and key and isinstance(value, (str, int, float, bool))
            for key, value in configured_environment.items()
        )
        if not valid_environment:
            raise ServiceError(f"[{section}].environment must be a table of scalar values")
        environment = dict(configured_environment)
        if self.profile is not None:
            environment.setdefault("GWAY_SERVICE_PROFILE", self.profile)
        working_directory = self.config.get("working_directory")
        if working_directory is not None and not isinstance(working_directory, str):
            raise ServiceError(f"[{section}].working_directory must be a string")
        lines = ["[Unit]", f"Description={description}"]
        if wants:
            lines.append(f"Wants={' '.join(wants)}")
        if requires:
            lines.append(f"Requires={' '.join(requires)}")
        if after:
            lines.append(f"After={' '.join(after)}")
        if on_failure:
            lines.append(f"OnFailure={' '.join(on_failure)}")
        lines.extend(
            [
                f"StartLimitIntervalSec={start_limit_interval_sec}",
                f"StartLimitBurst={start_limit_burst}",
                "",
                "[Service]",
                "Type=simple",
                f"User={_service_user(self.config, user)}",
            ]
        )
        log_environment = consumer_environment_file(self.project)
        if log_environment is not None:
            lines.append(f"EnvironmentFile={_unit_arg(log_environment)}")
        if working_directory:
            expanded = _expand(working_directory, self.project)
            lines.append(
                f"WorkingDirectory={_unit_path(expanded, f'[{section}].working_directory')}"
            )
        for key, value in environment.items():
            lines.append(f"Environment={_unit_arg(f'{key}={value}')}")
        lines.append(f"ExecStart={' '.join(_unit_arg(argument) for argument in command)}")
        lines.extend(
            [
                f"Restart={restart}",
                f"RestartSec={restart_sec}s",
                f"TimeoutStopSec={timeout_stop_sec}s",
                "",
                "[Install]",
                "WantedBy=multi-user.target",
                "",
            ]
        )
        return "\n".join(lines)

    def write(self, content: str) -> Path:
        self.unit_directory.mkdir(parents=True, exist_ok=True)
        temporary = self.unit_path.with_suffix(self.unit_path.suffix + ".tmp")
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, self.unit_path)
        return self.unit_path

    def uninstall(self) -> bool:
        existed = self.unit_path.exists()
        _systemctl("disable", "--now", self.unit_name, check=False)
        if existed:
            self.unit_path.unlink()
        _systemctl("reset-failed", self.unit_name, check=False)
        return existed

    def start(self) -> None:
        _systemctl("start", self.unit_name)

    def stop(self) -> None:
        _systemctl("stop", self.unit_name)

    def restart(self) -> None:
        _systemctl("restart", self.unit_name)

    def status(self) -> dict[str, object]:
        active = _systemctl("is-active", self.unit_name, check=False)
        enabled = _systemctl("is-enabled", self.unit_name, check=False)
        return {
            "project": self.project.name,
            "service": self.key,
            "unit": self.unit_name,
            "active": active.returncode == 0,
            "active_state": active.stdout.strip() or active.stderr.strip(),
            "enabled": enabled.returncode == 0,
            "enabled_state": enabled.stdout.strip() or enabled.stderr.strip(),
        }
