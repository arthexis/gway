"""Project-local GWAY manifest discovery and ingestion bootstrap."""

from pathlib import Path

from . import toml
from .ingestion.base import remember_object
from .ingestion.router import has_path_syntax


def find_manifest(start=None):
    """Return the nearest gway.toml from start/current directory upward."""
    root = Path.cwd() if start is None else Path(start)
    root = root.expanduser().resolve()
    if root.is_file():
        root = root.parent

    for directory in (root, *root.parents):
        manifest = directory / "gway.toml"
        if manifest.is_file():
            return manifest
    return None


def _project_name(data):
    project = data.get("project")
    if not isinstance(project, dict):
        return None
    name = project.get("name")
    return name if isinstance(name, str) and name.strip() else None


def _canonical_entries(value):
    if not isinstance(value, list):
        return None

    entries = []
    for index, entry in enumerate(value):
        if not isinstance(entry, dict):
            raise ValueError(f"[[ingest]] entry {index + 1} must be a table")
        if "source" not in entry:
            raise ValueError(f"[[ingest]] entry {index + 1} requires source")
        source = entry.get("source")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(
                f"[[ingest]] entry {index + 1} source must be a non-empty string"
            )
        entries.append(dict(entry))
    return entries


def _shorthand_entries(value, *, project_name=None):
    if not isinstance(value, dict):
        return None

    entries = []
    for kind, source in value.items():
        if not isinstance(kind, str) or not kind.strip():
            raise ValueError("[ingest] keys must be non-empty ingestor names")
        if not isinstance(source, str) or not source.strip():
            raise ValueError(
                f"[ingest].{kind} must be a non-empty source string"
            )
        entry = {"kind": kind, "source": source}
        if kind == "django" and project_name is not None:
            entry["name"] = project_name
        entries.append(entry)
    return entries


def ingestion_entries(data):
    """Return normalized declarative ingestion entries from manifest data."""
    if not isinstance(data, dict):
        raise ValueError("gway.toml root must be a table")

    value = data.get("ingest")
    if value is None:
        return []

    project_name = _project_name(data)
    entries = _canonical_entries(value)
    if entries is None:
        entries = _shorthand_entries(value, project_name=project_name)
    if entries is None:
        raise ValueError("[ingest] must be a table or [[ingest]] array")

    for entry in entries:
        if (
            entry.get("kind") == "django"
            and "name" not in entry
            and project_name is not None
        ):
            entry["name"] = project_name
    return entries


def _source_from_manifest(source, directory):
    """Resolve filesystem-shaped declaration sources from manifest directory."""
    if not isinstance(source, str):
        return source

    from .ingestion.url import is_url

    if is_url(source):
        return source

    candidate = Path(source).expanduser()
    manifest_candidate = candidate
    if not candidate.is_absolute():
        manifest_candidate = directory / candidate

    if has_path_syntax(source) or manifest_candidate.exists():
        return manifest_candidate.resolve()
    return source


def _django_name_from_source(source):
    """Infer a declarative Django mount name from a concrete project path."""
    if not isinstance(source, Path):
        return None

    path = source.expanduser().resolve()
    if path.is_file() and path.name == "manage.py":
        return path.parent.name or None
    if path.is_dir() and (path / "manage.py").is_file():
        return path.name or None
    return None


def load_ingestions(runtime, manifest):
    """Load declarative ingestion entries into one Gateway."""
    manifest = Path(manifest).expanduser().resolve()
    data = toml.load(manifest)
    entries = ingestion_entries(data)

    loaded = []
    for entry in entries:
        options = dict(entry)
        source = options.pop("source")
        source = _source_from_manifest(source, manifest.parent)

        if options.get("kind") == "django" and "name" not in options:
            inferred = _django_name_from_source(source)
            if inferred is not None:
                options["name"] = inferred

        loaded.append(runtime.ingest(source, **options))
    return loaded


def _declares_ingestion(manifest):
    """Return whether a manifest contains an ingestion table declaration."""
    for raw in Path(manifest).read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line in {"[ingest]", "[[ingest]]"}:
            return True
    return False



def _valid_installation(record, paths):
    """Return whether one registry record still names a managed project tree."""
    expected = (paths.projects / record.name).resolve()
    try:
        installed = record.install_path.expanduser().resolve()
    except (OSError, RuntimeError):
        return False
    if installed != expected:
        return False
    if not installed.is_dir():
        return False
    return (installed / "gway.toml").is_file()


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




def project_aliases(manifest):
    """Return validated aliases declared by one project manifest."""
    from .install.model import validate_name

    data = toml.load(manifest)
    project = data.get("project") if isinstance(data, dict) else None
    values = project.get("aliases", ()) if isinstance(project, dict) else ()
    if values is None:
        return ()
    if not isinstance(values, list):
        raise ValueError("[project].aliases must be an array of names")

    aliases = []
    for value in values:
        try:
            alias = validate_name(value)
        except ValueError as exc:
            raise ValueError(f"Invalid project alias: {exc}") from exc
        if alias not in aliases:
            aliases.append(alias)
    return tuple(aliases)


def expand_installed_project(runtime, installation, *, path=None):
    """Load one installed project's declarative ingestion exactly once."""
    record = remember_object(
        runtime,
        installation,
        path or (installation.name,),
        expander=expand_installed_project,
    )
    if record.expanded:
        return []

    manifest = installation.install_path / "gway.toml"
    if not manifest.is_file():
        raise RuntimeError(
            f"Installed project {installation.name!r} has no gway.toml"
        )

    loaded = load_ingestions(runtime, manifest)
    record.expanded = True
    return loaded


def discover_managed_projects(runtime):
    """Remember installed user/system projects and declared lazy aliases."""
    discovered = {}
    aliases = {}
    for system in (False, True):
        try:
            records = discover_installations(system=system)
        except (OSError, PermissionError):
            continue
        for record in records:
            if record.name in discovered:
                continue
            discovered[record.name] = record
            branch = remember_object(
                runtime,
                record,
                (record.name,),
                expander=expand_installed_project,
            )
            for alias in project_aliases(record.install_path / "gway.toml"):
                if alias == record.name:
                    continue
                if alias in discovered:
                    raise RuntimeError(
                        f"Installed project alias {alias!r} conflicts with "
                        "an installed project name"
                    )
                owner = aliases.get(alias)
                if owner is not None and owner != record.name:
                    raise RuntimeError(
                        f"Installed project alias {alias!r} is declared by "
                        f"both {owner!r} and {record.name!r}"
                    )
                aliases[alias] = record.name
                branch.paths.add((alias,))

    runtime._installed = discovered
    runtime._installed_aliases = aliases
    return discovered


def bootstrap(runtime, *, start=None):
    """Discover managed projects and apply the nearest local project manifest."""
    discover_managed_projects(runtime)

    manifest = find_manifest(start)
    if manifest is None:
        return None

    runtime._manifest_path = manifest
    if _declares_ingestion(manifest):
        load_ingestions(runtime, manifest)
    return manifest
