"""Recipe dependency declaration, preflight, and activation."""

from ..tokens import chunk, is_literal, token_value
from .path import companion_path


def collect_recipe_requirements(statement_list):
    """Collect declarative requirements without changing recipe execution order."""
    collected = {"python": []}
    for statement in statement_list:
        for stage in chunk(statement):
            if not stage:
                continue
            first = stage[0]
            if is_literal(first) or token_value(first) != "require":
                continue
            packages = []
            index = 1
            while index < len(stage):
                raw = stage[index]
                value = token_value(raw)
                if not is_literal(raw) and value.startswith("--"):
                    if value != "--python":
                        raise TypeError(f"Unknown require argument {value}")
                    index += 1
                    continue
                packages.append(value)
                index += 1
            if not packages:
                raise TypeError("require needs at least one package")
            for package in packages:
                package = str(package).strip()
                if not package:
                    raise ValueError("require package names must be non-empty strings")
                if package not in collected["python"]:
                    collected["python"].append(package)
    return collected if collected["python"] else {}


def prepare_required_companion(runtime, frame):
    """Converge requirements and start a managed companion before execution."""
    requirements = frame.preflight_requirements.get("python", ())
    if not requirements:
        return

    from .environment import environment_python, sync_python_environment
    from .uv import ensure_uv

    frame.uv = ensure_uv(
        system=getattr(frame.environment, "scope", "user") == "system"
    )
    sync_python_environment(frame.environment, frame.uv, requirements)

    companion = companion_path(frame.path)
    if companion is None:
        return

    from .companion import CompanionWorker, unregister_worker_operations

    worker = CompanionWorker.start(
        frame.path,
        companion,
        environment_python(frame.environment),
    )
    frame.companion_worker = worker
    unregister_worker_operations(runtime, worker)
