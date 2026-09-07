# GWAY Redesign Plan

## Goal

Rebuild `arthexis/gway` as a lightweight project manager and universal command dispatcher for the Arthexis/GWAY ecosystem.

The new GWAY should let a fresh machine install one small executable, discover trusted projects from GitHub, install them into isolated local environments, and expose their native command surfaces through a uniform CLI.

The defining idea is:

> GWAY turns GitHub-hosted projects into installable, discoverable command namespaces.

The old implementation has been preserved in `arthexis/gway-legacy`. The new repository should reuse its strongest ideas, especially automatic CLI generation from Python functions, without carrying forward its bundled utility collection, large dependency surface, or tight framework-specific assumptions.

## User experience

The common command shape is:

```text
gway <project> <command> [arguments]
```

Core GWAY lifecycle commands remain top-level:

```text
gway list
gway search
gway install wireguard
gway update wireguard
gway remove wireguard
gway info wireguard
gway path wireguard
```

Installed projects then become namespaces:

```text
gway wireguard status
gway wireguard peer add --name gway-004 --address 10.44.0.4
gway box provision
gway rpi-ops network status

gway arthexis check
gway arthexis migrate
gway arthexis collectstatic
```

Framework details should normally stay hidden. A user should not need to know whether a command was generated from a Python function, a Django `BaseCommand`, or another supported adapter.

## Design principles

1. **GitHub is the discovery and distribution boundary.** Projects no longer live inside a central `projects/` directory.
2. **Projects own their command surface.** GWAY discovers commands rather than hard-coding them centrally.
3. **Automatic CLI generation remains a core feature.** Python signatures and framework-native command metadata should drive the CLI whenever possible.
4. **Adapters isolate framework differences.** Python projects and Django projects present the same GWAY command model through different discovery/execution adapters.
5. **GWAY itself stays small.** Domain libraries and application dependencies belong in managed projects, not in the dispatcher.
6. **Projects are isolated.** Each managed project should have its own checkout and runtime environment.
7. **Trusted-by-default.** Automatic discovery initially targets approved owners, starting with `arthexis`.
8. **Convention before configuration.** A small manifest selects the adapter and entrypoint; command definitions remain in the project code.
9. **The CLI contract is more important than implementation language.** Future adapters may support additional project types without changing `gway PROJECT COMMAND`.
10. **Legacy behavior is not silently reproduced.** Old features return only when they solve a demonstrated need in the new architecture.

## High-level architecture

```text
                 GitHub repositories
                        |
                        v
                    gway.toml
                        |
                        v
                Repository Manager
          resolve / clone / update / remove
                        |
                        v
                      Project
       metadata / checkout / environment / revision
                        |
                        v
                  Adapter selection
                /                   \
               v                     v
        PythonAdapter          DjangoAdapter
               \                     /
                v                   v
                 Common command model
                        |
                        v
                    Dispatcher
                        |
                        v
                        CLI
              gway PROJECT COMMAND ...
```

The major internal responsibilities should be separated rather than collected in a single large `Gateway` object:

```text
RepositoryManager
    GitHub resolution, cloning, updating, removal

Project
    metadata, paths, revision, environment

Adapter
    discover commands, describe commands, execute commands

Command
    framework-neutral command metadata

Dispatcher
    resolve project + command path

CLI
    build argparse interface and render help/output

Runner
    execute in the correct project environment
```

## Repository layout

Target structure:

```text
gway/
├── pyproject.toml
├── README.md
├── PLAN.md
├── AGENTS.md
├── src/
│   └── gway/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── command.py
│       ├── config.py
│       ├── project.py
│       ├── registry.py
│       ├── repository.py
│       ├── runner.py
│       └── adapters/
│           ├── __init__.py
│           ├── base.py
│           ├── python.py
│           └── django.py
└── tests/
```

Names may evolve during implementation, but responsibilities should remain separated.

## Project manifest

Each managed repository should expose a small `gway.toml` at its root.

### Python project

```toml
[project]
name = "wireguard"
aliases = ["wg"]

[adapter]
type = "python"
module = "gway_wireguard.gway"
```

The module may be either a single module or a package namespace.

### Django project

```toml
[project]
name = "arthexis"

[adapter]
type = "django"
manage = "manage.py"
settings = "arthexis.settings"
```

`settings` should be optional when the project already configures `DJANGO_SETTINGS_MODULE` through its normal startup path.

The manifest should describe how GWAY enters a project. It should not duplicate the project's full command list.

## Common command model

Adapters should expose commands through a framework-neutral representation, for example:

```python
@dataclass
class Command:
    path: tuple[str, ...]
    summary: str | None
    description: str | None
    parameters: list[Parameter]
    adapter_data: object | None = None
```

The exact model can stay minimal in the first implementation. Its purpose is to let the CLI handle discovery and help consistently without knowing the underlying framework.

The base adapter contract should be approximately:

```python
class ProjectAdapter:
    def commands(self) -> Iterable[Command]: ...
    def describe(self, path: tuple[str, ...]) -> Command: ...
    def run(self, path: tuple[str, ...], argv: list[str]) -> object: ...
```

This interface should remain small. Adapter-specific execution details should not leak into the dispatcher.

## Python adapter

The Python adapter carries forward the most useful part of legacy GWAY: public Python functions automatically becoming CLI commands.

Recommended project convention:

```text
src/gway_wireguard/
└── gway/
    ├── __init__.py
    ├── peer.py
    ├── service.py
    └── diagnostics.py
```

Example:

```python
def status():
    """Show WireGuard status."""


def add(
    name: str,
    address: str,
    *,
    enabled: bool = True,
):
    """Add a peer."""
```

This should automatically produce commands such as:

```text
gway wireguard status
gway wireguard peer add NAME ADDRESS
gway wireguard peer add NAME ADDRESS --no-enabled
```

The adapter should preserve these useful legacy behaviors:

- public function discovery;
- nested module namespaces;
- `snake_case` to `kebab-case` command names;
- `inspect.signature()` driven argument generation;
- type-hint conversion for common scalar types;
- docstrings as CLI help;
- booleans exposed as `--flag` / `--no-flag`;
- positional, keyword-only, `*args`, and basic optional arguments;
- ordinary Python return values passed back to the common output layer.

Initial type conversion support should focus on:

```text
str
int
float
bool
pathlib.Path
Optional[T]
Literal[...]
```

More advanced typing should be added only after real project needs appear.

### Optional command metadata

Convention should be sufficient for most projects, but lightweight decorators may later allow exceptions:

```python
from gway import command

@command(name="check", aliases=["doctor"])
def diagnostics():
    ...
```

or:

```python
@command(hidden=True)
def internal_repair():
    ...
```

Decorators should remain optional. Importing GWAY should not be required merely to expose ordinary public functions unless metadata is needed.

## Django adapter

Django should be a first-class adapter rather than a special case inside Arthexis.

Django already has a discoverable command system through management commands. The adapter should reuse that system rather than implementing an independent CLI schema.

Conceptually:

```python
from django.core.management import get_commands, load_command_class

commands = get_commands()
command = load_command_class(app_name, command_name)
parser = command.create_parser("gway arthexis", command_name)
```

That parser already describes positional arguments and options such as those used by `migrate`, `check`, `collectstatic`, and project-specific management commands.

The desired experience is:

```text
gway arthexis migrate
gway arthexis check
gway arthexis shell
gway arthexis createsuperuser
gway arthexis collectstatic
gway arthexis <custom-command>
```

not:

```text
gway arthexis django migrate
```

The adapter type is an implementation detail.

For normal execution, prefer Django's management API after bootstrapping the project environment. A subprocess call through `manage.py` may remain as a compatibility fallback for commands whose behavior makes in-process invocation unsuitable.

The Django adapter should eventually preserve the command parser's native help and option behavior instead of flattening everything into strings.

## Future adapters

Version 1 should implement only:

- `python`
- `django`

The internal adapter abstraction should make later additions possible without designing them now. Possible future adapters include:

- executable/shell entrypoints;
- Odoo;
- FastAPI-specific operations;
- systemd service projects;
- Docker Compose;
- npm or Cargo projects.

No future adapter should be added until there is a concrete repository that needs it.

## Project resolution

Initially, GWAY should resolve short project names against trusted GitHub naming conventions.

Examples:

```text
wireguard  -> arthexis/gway-wireguard
rpi-ops    -> arthexis/gway-rpi-ops
box        -> arthexis/gway-box
arthexis   -> arthexis/arthexis
```

Resolution order can start with:

1. exact configured alias;
2. `arthexis/gway-<name>`;
3. `arthexis/<name>`.

Explicit repository identifiers should also be supported:

```text
gway install arthexis/gway-wireguard
```

Automatic arbitrary-owner execution should not be enabled initially.

## Trust model

Default configuration should trust only approved owners:

```toml
[github]
owners = ["arthexis"]
```

Installing from an owner outside that list should require an explicit trust action or override.

Later hardening may add:

- pinned commits;
- stable/beta channels;
- release-only installation;
- signed releases or attestations;
- checksums;
- allowlisted repositories;
- update policies.

These should not block the first functional version.

## Local state and installation

Normal user installs should use platform-appropriate user directories, approximately:

```text
~/.config/gway/config.toml
~/.local/share/gway/projects/
~/.local/share/gway/environments/
~/.local/share/gway/state.json
```

A system/appliance mode should support paths such as:

```text
/opt/gway/projects/
/opt/gway/environments/
/opt/gway/state/
```

Each project should have:

- its own checkout;
- its own runtime environment where applicable;
- recorded repository URL;
- current commit SHA;
- branch/tag/channel metadata;
- adapter metadata;
- install/update timestamp.

GWAY itself should not absorb project dependencies.

## Installation lifecycle

A first-class install should eventually follow this sequence:

```text
resolve project name
    -> resolve GitHub repository
    -> validate owner trust
    -> clone repository
    -> read gway.toml
    -> select adapter
    -> prepare project environment
    -> install project dependencies
    -> validate adapter discovery
    -> record installed state
```

Update should:

```text
fetch
    -> update selected branch/tag/channel
    -> refresh dependencies if needed
    -> validate manifest/adapter
    -> record new revision
```

Removal should remove managed checkout/environment/state without touching unrelated user files.

## Core CLI resolution

Dispatch should follow a simple rule:

```text
gway TOKEN ...

TOKEN is a core command?
    yes -> execute GWAY core command
    no  -> resolve TOKEN as an installed project
           -> load project metadata
           -> select adapter
           -> discover command namespace
           -> dispatch remaining tokens
```

Explicit `gway run <project> ...` may be retained as a diagnostic or scripting form, while `gway <project> ...` is the normal interface.

## Output model

Project commands should be able to return ordinary values. GWAY should own final rendering.

Initial behavior can be simple:

- strings print directly;
- dictionaries/lists get readable structured output;
- `--json` serializes compatible return values;
- integer process status is reserved for explicit command/adapter execution semantics rather than inferred from arbitrary returned integers.

Legacy result/context chaining should not be part of the first implementation.

## What to reuse from gway-legacy

The new implementation should reuse ideas and, where practical, extract focused code from `gway-legacy`, especially from the old console/introspection path:

- function signature inspection;
- `typing.get_type_hints()` handling;
- argument conversion;
- boolean flag generation;
- public function discovery;
- docstring/help extraction;
- nested namespace resolution;
- `--json` output behavior where it remains cleanly separable.

Any reused code should be moved into small components with new tests rather than copying the legacy `Gateway` object wholesale.

## What not to port initially

Do not bring these into the first new GWAY implementation:

- bundled `projects/` utilities;
- Django model fallback through `arthexis.settings`;
- the global mutable `gw` execution context;
- result/context/env resolution chains;
- sigils;
- `.gwr` recipes;
- automatic env/client/server inheritance;
- watchers;
- GUI/audio/application-specific helpers;
- help SQLite database;
- broad legacy dependency list.

These can be reconsidered individually after the new project manager and adapters work end-to-end.

## Relationship to Arthexis

Arthexis should become a managed project, not a dependency of GWAY.

```text
gway install arthexis
gway arthexis check
gway arthexis migrate
gway arthexis <custom-management-command>
```

GWAY should contain generic Django knowledge only. It should not contain Arthexis-specific settings imports, model lookup logic, or command definitions.

## Relationship to gway-box

`gway-box` should become an appliance definition and provisioning project built on top of GWAY rather than the place where project management logic lives.

A box definition could eventually describe the projects a device requires, for example:

```text
gway-wireguard
gway-rpi-ops
gway-ap-kiosk
gway-agent-ops
```

A fresh machine should eventually be able to bootstrap toward:

```text
install gway
gway install box
gway box provision
```

`gway-box` may call core GWAY lifecycle APIs to install the rest of the appliance stack.

# Implementation chunks

Each chunk below should be small enough to implement, review, merge, and validate independently. Later chunks may refine earlier interfaces, but each should leave `main` in a coherent state.

## Chunk 0 - Establish the generation break

**Purpose:** make the repository clearly represent the new project while preserving the old implementation separately.

Work:

- confirm `gway-legacy` contains the preserved legacy history;
- replace legacy-oriented repository documentation with a concise new README;
- update `AGENTS.md` so agents no longer follow legacy architecture rules;
- establish a fresh `src/gway` package layout;
- keep package name and executable name `gway`;
- choose the new major version line (`1.0.0.dev0` or equivalent);
- reduce runtime dependencies to the minimum needed by the new skeleton.

Acceptance:

```text
python -m gway --help
gway --help
```

both execute a minimal new CLI, with tests confirming no legacy project modules are imported.

## Chunk 1 - Project metadata and local registry

**Purpose:** represent installed projects before implementing GitHub installation.

Work:

- `Project` model;
- config/data directory resolution;
- `gway.toml` parser;
- local installed-project registry/state;
- `gway list`;
- `gway info <project>`;
- `gway path <project>`;
- fixture projects for tests.

Acceptance:

GWAY can discover and describe manually registered/local fixture projects without network access.

## Chunk 2 - Adapter contract and common command model

**Purpose:** establish the framework boundary before implementing actual adapters.

Work:

- `ProjectAdapter` protocol/base class;
- common `Command` and parameter metadata;
- adapter factory from manifest;
- dispatcher that distinguishes core commands from project namespaces;
- error model for unknown project/adapter/command.

Acceptance:

A fake test adapter can expose commands through:

```text
gway fixture hello
```

without the CLI knowing adapter-specific details.

## Chunk 3 - Python adapter MVP

**Purpose:** restore automatic CLI generation from Python functions.

Work:

- import manifest-declared module/package;
- discover public functions;
- discover nested public modules;
- convert names to kebab-case;
- inspect signatures and type hints;
- generate argparse parameters;
- render docstrings in help;
- execute functions and render results;
- implement `--json` for compatible values.

Initial type support:

```text
str, int, float, bool, Path, Optional, Literal
```

Acceptance:

A fixture matching the future `gway-wireguard` style can expose nested functions entirely through introspection, with no handwritten parser.

## Chunk 4 - GitHub repository resolution and install

**Purpose:** make GWAY a real project manager rather than only a local dispatcher.

Work:

- trusted-owner configuration;
- short-name repository resolution;
- explicit `owner/repo` resolution;
- clone into managed project directory;
- read/validate `gway.toml` after clone;
- create project environment where required;
- install Python project dependencies;
- record repository and revision state;
- implement `gway install`.

Acceptance:

A clean environment can install one small Python-adapter project from GitHub and immediately run a discovered command.

## Chunk 5 - Convert gway-wireguard as the reference project

**Purpose:** validate the Python adapter against a real Raspberry Pi project before expanding the framework.

Work in `gway-wireguard`:

- add `gway.toml`;
- expose a deliberate `gway` Python namespace;
- move/wrap suitable operations into public functions;
- ensure helpers remain private;
- validate generated help and booleans/types;
- document `gway wireguard ...` usage.

Acceptance on a development machine and then a Pi:

```text
gway install wireguard
gway wireguard --help
gway wireguard status
```

works without a handwritten WireGuard CLI parser in GWAY.

This is the first end-to-end milestone.

## Chunk 6 - Django adapter MVP

**Purpose:** support Arthexis and generic Django repositories without project-specific code in GWAY.

Work:

- load Django project from manifest;
- configure environment and call `django.setup()`;
- discover management commands with `get_commands()`;
- load `BaseCommand` instances;
- reuse their parser metadata/help;
- execute through Django's management API where practical;
- retain subprocess fallback if required;
- test against a minimal fixture Django project.

Acceptance:

```text
gway django-fixture check
gway django-fixture migrate --plan
```

uses Django's own command definitions through the adapter.

## Chunk 7 - Convert Arthexis

**Purpose:** prove the Django adapter on the main application.

Work in `arthexis/arthexis`:

- add `gway.toml` with Django adapter metadata;
- ensure project setup works from a managed GWAY checkout/environment;
- validate built-in and custom management commands;
- document GWAY invocation for development and appliance contexts.

Acceptance:

```text
gway install arthexis
gway arthexis check
gway arthexis migrate --plan
```

works without Arthexis-specific code in the GWAY repository.

This is the second end-to-end milestone.

## Chunk 8 - Convert gway-epaper

**Purpose:** validate the Python adapter against another hardware-facing Raspberry Pi project after the Django/Arthexis milestone.

Work in `gway-epaper`:

- add/validate `gway.toml` with a deliberate Python command namespace;
- expose ordinary typed Python functions for the intended operator surface;
- keep display/backend dependencies and hardware-specific logic inside the managed project environment;
- ensure GWAY owns command discovery, generated help, aliases, type conversion, JSON rendering, and dispatch;
- keep helpers and any low-level bootstrap paths private to the project rather than maintaining a competing GWAY-facing parser;
- document `gway epaper ...` usage.

Acceptance on a development machine and then the target Raspberry Pi/ePaper hardware:

```text
gway install epaper
gway epaper --help
```

plus one hardware-independent diagnostic/status command on a development machine and the relevant display command validation on target hardware.

## Chunk 9 - Update and remove lifecycle

**Purpose:** make installed projects maintainable.

Work:

- `gway update <project>`;
- `gway update` for all managed projects;
- safe branch/tag revision handling;
- dependency refresh policy;
- revision tracking;
- `gway remove <project>`;
- cleanup of managed environments/state;
- useful dirty-checkout handling.

Acceptance:

A project can be installed, updated to a newer revision, inspected, and removed without manual Git operations.

## Chunk 10 - Appliance/system installation mode

**Purpose:** support Debian/Raspberry Pi boxes cleanly.

Work:

- explicit user vs system roots;
- `/opt/gway` project/environment/state support;
- permission and ownership rules;
- non-interactive operation suitable for provisioning;
- stable executable placement;
- installation/bootstrap documentation.

Acceptance:

A clean Debian/RPi environment can install GWAY system-wide and manage projects without relying on a developer home directory.

## Chunk 11 - Convert gway-box and remaining operational projects

**Purpose:** make the new GWAY the common entrypoint for appliance projects.

Candidate conversions:

- `gway-box`;
- `gway-rpi-ops`;
- `gway-ap-kiosk`;
- `gway-agent-ops`;
- other maintained `gway-*` repositories.

`gway-box` should become the composition/provisioning layer and call GWAY lifecycle APIs rather than implementing another package manager.

Acceptance:

A fresh box can progress toward:

```text
install gway
gway install box
gway box provision
```

and have the required operational repositories installed and runnable through GWAY.

## Chunk 12 - CLI polish and completion

**Purpose:** improve usability after architecture and lifecycle are stable.

Work may include:

- shell completion;
- richer `gway search`;
- command aliases;
- improved nested help;
- consistent exit/error rendering;
- JSON metadata/discovery output;
- `gway doctor` for registry/environment diagnostics.

Do not prioritize this before both Python and Django end-to-end paths work.

## Chunk 13 - Re-evaluate legacy features

Only after the new architecture is in production use, evaluate whether any legacy features deserve clean reimplementation:

- Python API such as `project("wireguard").peer.add(...)`;
- command chaining;
- recipes;
- context/result propagation;
- aliases/decorators beyond basic metadata.

Features should return because a current workflow needs them, not solely for backwards compatibility.

# Milestone sequence

The shortest path to a useful system is:

```text
new skeleton
  -> local registry
  -> adapter abstraction
  -> Python adapter
  -> GitHub install
  -> gway-wireguard end-to-end
  -> Django adapter
  -> Arthexis end-to-end
  -> gway-epaper end-to-end
  -> update/remove
  -> system install
  -> gway-box provisioning
```

The critical architectural checkpoint is after `gway-wireguard`: at that point the core promise of installing a GitHub project and automatically turning its Python API into a CLI should be proven before Django or appliance complexity is added.

The critical ecosystem checkpoint is after Arthexis: at that point one GWAY command model should successfully cover both native GWAY-style Python repositories and generic Django projects through adapters. The subsequent `gway-epaper` milestone then validates that the same Python-adapter contract scales cleanly to another hardware-facing project before lifecycle and appliance work expands.

# Versioning and compatibility

The existing PyPI name `gway` currently represents the legacy dispatcher. The intended semantic break is:

```text
gway 0.x  -> legacy dispatcher
gway 1.x  -> GitHub project manager + adapter dispatcher
```

Before publishing 1.0, the final 0.x release should clearly document that the next major version changes the architecture and that the historical source is preserved in `arthexis/gway-legacy`.

Do not attempt to make `gway` and a repackaged `gway-legacy` coexist in one Python environment unless a concrete compatibility requirement justifies restructuring the old import package.

# Definition of the first production-ready release

GWAY 1.0 should not require every possible adapter or migrated repository. It should be considered ready when it can reliably:

1. install itself as a small standalone package;
2. resolve trusted GitHub projects;
3. install/update/remove managed projects in isolated environments;
4. inspect and dispatch Python-adapter projects with automatic CLI generation;
5. inspect and dispatch Django management commands through the Django adapter;
6. run at least `gway-wireguard` and Arthexis end-to-end;
7. support both user installations and the Debian/Raspberry Pi system layout needed by GWAY boxes;
8. report installed repository/revision/environment metadata clearly;
9. operate without importing the old bundled project collection or its large dependency set.