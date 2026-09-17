from __future__ import annotations

from collections.abc import Callable, Sequence

from ..registry import Registry
from ..upgrade import UpgradeError, Upgrader
from .project import upgrade_status

UpgradeCallback = Callable[[dict[str, object]], None]
UpgraderFactory = Callable[[Registry], Upgrader]


def run_upgrade(
    registry: Registry,
    *,
    projects: Sequence[str] = (),
    all_projects: bool = False,
    upgrade_self: bool | None = None,
    force: bool = False,
    try_force: bool = False,
    reload: bool = False,
    arguments: Sequence[str] = (),
    upgrader_factory: UpgraderFactory = Upgrader,
    on_completed: UpgradeCallback | None = None,
) -> object:
    targets = list(dict.fromkeys(projects))
    if targets and (all_projects or upgrade_self is not None):
        raise UpgradeError("PROJECTS cannot be combined with --all, --self, or --no-self")

    include_self_target = "gway" in targets
    managed_targets = [target for target in targets if target != "gway"]
    if arguments and len(managed_targets) != 1:
        raise UpgradeError("installer arguments require exactly one managed PROJECT")

    upgrader = upgrader_factory(registry)
    results: list[dict[str, object]] = []

    def completed(record: dict[str, object]) -> None:
        results.append(record)
        if on_completed is not None:
            on_completed(record)

    def upgrade_gway() -> None:
        upgrader.upgrade_self()
        completed(
            {
                "status": "upgraded",
                "name": "gway",
                "repository": "arthexis/gway",
                "revision": "main",
            }
        )

    upgrade_kwargs = {"try_force": True} if try_force else {}

    if targets:
        if include_self_target:
            upgrade_gway()
        for target in managed_targets:
            result = upgrader.project_result(
                target,
                force=force,
                reload=reload,
                arguments=arguments if len(managed_targets) == 1 else (),
                **upgrade_kwargs,
            )
            completed(upgrade_status("upgraded" if result.changed else "skipped", result))
        if len(managed_targets) == 1 and not include_self_target:
            return results[0]
        return results

    default_mode = not all_projects and upgrade_self is None
    include_self = upgrade_self is True or (upgrade_self is None and (default_mode or all_projects))
    include_projects = all_projects or default_mode or upgrade_self is False

    if include_self:
        upgrade_gway()
    if include_projects:
        for result in upgrader.all_project_results(
            force=force,
            reload=reload,
            **upgrade_kwargs,
        ):
            completed(upgrade_status("upgraded" if result.changed else "skipped", result))
    return results
