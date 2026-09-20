"""Convention-driven project discovery and ingestion bootstrap."""

from pathlib import Path

from .ingestion.base import remember_object


def find_project_file(start=None):
    """Return the nearest pyproject.toml, if any."""
    root = Path.cwd() if start is None else Path(start)
    root = root.expanduser().resolve()
    if root.is_file():
        root = root.parent
    for directory in (root, *root.parents):
        project_file = directory / "pyproject.toml"
        if project_file.is_file():
            return project_file
    return None



def project_variables(data):
    """Return semantic variables declared under [tool.gway.variables]."""
    if not isinstance(data, dict):
        return {}
    tool = data.get("tool")
    gway = tool.get("gway") if isinstance(tool, dict) else None
    variables = gway.get("variables") if isinstance(gway, dict) else None
    if variables is None:
        return {}
    if not isinstance(variables, dict):
        raise ValueError("[tool.gway.variables] must be a table")
    return dict(variables)


def _valid_installation(record, paths):
    """Return whether one registry record still names a managed project tree."""
    expected = (paths.projects / record.name).resolve()
    try:
        installed = record.install_path.expanduser().resolve()
    except (OSError, RuntimeError):
        return False
    return (
        installed == expected
        and installed.is_dir()
        and (installed / "pyproject.toml").is_file()
    )


def discover_installations(*, system=False):
    """Return valid Gway-managed installation records for one scope."""
    from .install import InstallState, install_paths

    paths = install_paths(system=system)
    state = InstallState(paths.state)
    return [
        record
        for record in state.all(scope=paths.scope)
        if _valid_installation(record, paths)
    ]


def _script_aliases(runtime, project, command):
    """Return a bare alias only when one project owns that script name."""
    owners = getattr(runtime, "_script_owners", {}).get(command, ())
    return (command,) if owners == (project,) else ()


def load_project_scripts(runtime, root, project):
    """Expose [project.scripts] as callable Gway operations."""
    from .ingestion.base import IngestedOperation, register_operation
    from .project import project_scripts, resolve_target

    wrapped = []
    for command, target in project_scripts(root).items():
        callable_ = resolve_target(root, target)
        operation = IngestedOperation(
            (project, command),
            callable_,
            source=Path(root),
            kind="project-script",
            aliases=_script_aliases(runtime, project, command),
            op=command,
            sub=project,
            metadata={
                "project": project,
                "root": Path(root),
                "script": command,
                "target": target,
            },
        )
        wrapped.append(register_operation(runtime, operation))
    return wrapped


def load_project_main_packages(runtime, root, project=None):
    """Expose conventional package __main__ entrypoints from a project tree."""
    from dataclasses import replace

    from .project import import_project_module, main_packages

    root = Path(root).expanduser().resolve()
    wrapped = []
    for name in main_packages(root):
        module = import_project_module(root, name)
        wrapped.extend(runtime.ingest(module, path=tuple(name.split("."))))

        launchable = runtime.launchables.resolve(name)
        if launchable is not None:
            metadata = dict(launchable.metadata)
            metadata["root"] = root
            if project is not None:
                metadata["project"] = project
            runtime.launchables.register(
                replace(
                    launchable,
                    root=root,
                    metadata=metadata,
                )
            )
    return wrapped


def expand_installed_project(runtime, installation, *, path=None):
    """Load one installed project's conventional execution surface once."""
    record = remember_object(
        runtime,
        installation,
        path or (installation.name,),
        expander=expand_installed_project,
    )
    if record.expanded:
        return []

    loaded = load_project_scripts(
        runtime,
        installation.install_path,
        installation.name,
    )
    loaded.extend(
        load_project_main_packages(
            runtime,
            installation.install_path,
            installation.name,
        )
    )
    record.expanded = True
    return loaded


def discover_managed_projects(runtime):
    """Remember installed projects and their lazy conventional entrypoints."""
    discovered = {}
    for system in (False, True):
        try:
            records = discover_installations(system=system)
        except (OSError, PermissionError):
            continue
        for record in records:
            discovered.setdefault(record.name, record)

    from .project import project_scripts

    script_owners = {}
    for name, record in discovered.items():
        for command in project_scripts(record.install_path):
            script_owners.setdefault(command, []).append(name)
    runtime._script_owners = {
        command: tuple(owners)
        for command, owners in script_owners.items()
    }

    for name, record in discovered.items():
        remember_object(
            runtime,
            record,
            (name,),
            expander=expand_installed_project,
        )

    runtime._installed = discovered

    from .souschef.discovery import discover as discover_souschef

    discover_souschef(runtime, discovered.values())
    return discovered


def bootstrap(runtime, *, start=None):
    """Discover managed and local pyproject-based execution surfaces."""
    discover_managed_projects(runtime)

    project_file = find_project_file(start)
    if project_file is None:
        return None

    runtime._project_path = project_file

    from . import toml

    data = toml.load(project_file)
    variables = project_variables(data)
    if variables:
        runtime.append_source(variables, name="pyproject")

    project_data = data.get("project") if isinstance(data, dict) else None
    project_name = (
        project_data.get("name")
        if isinstance(project_data, dict)
        else None
    )
    if isinstance(project_name, str) and project_name.strip():
        from .project import project_scripts

        owners = {
            command: list(projects)
            for command, projects in getattr(runtime, "_script_owners", {}).items()
        }
        for command in project_scripts(project_file.parent):
            owners.setdefault(command, [])
            if project_name not in owners[command]:
                owners[command].append(project_name)
        runtime._script_owners = {
            command: tuple(projects)
            for command, projects in owners.items()
        }
        load_project_scripts(runtime, project_file.parent, project_name)
        load_project_main_packages(
            runtime,
            project_file.parent,
            project_name,
        )

    from .souschef.discovery import discover as discover_souschef

    discover_souschef(
        runtime,
        getattr(runtime, "_installed", {}).values(),
        local_project_file=project_file,
    )
    return project_file
