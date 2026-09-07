# GWAY

GWAY is a lightweight project manager and command dispatcher for the Arthexis/GWAY ecosystem.

The new 1.x generation discovers and manages projects from GitHub and exposes each project's commands through a common `gway <project> <command>` interface. Framework-specific command discovery is provided by adapters; the first planned adapters are Python function introspection and Django management commands.

GWAY also keeps a first-class Python API. The intended stable import is:

```python
from gway import gway as gw

# Mirrors the CLI namespace once the relevant managed projects are installed.
gw.wireguard.status()
gw.arthexis.check()
```

`from gway import gw` remains available as a compatibility alias. The Python facade will use the same registry, adapter, dispatcher, and runner as the CLI rather than bypassing managed project isolation.

## Sigils on the CLI

`gway-sigils` is GWAY's single runtime dependency and provides the `sigils` Python package used as part of the command-value language. Project names and command paths stay literal for predictable routing; argument values are interpolated before adapter parsing.

```bash
gway web build --output "[project.path]/dist"
gway ocpp connect --label "%[cwd]-[project.name]"
```

`%[...]` expressions are captured eagerly before the project-aware lazy context is built. `[...]` expressions resolve immediately before the selected adapter parses the command arguments.

The built-in GWAY context includes:

- `[cwd]` and `[home]`
- `[gway.config_dir]` and `[gway.data_dir]`
- `[project.name]`, `[project.path]`, `[project.adapter]`, `[project.aliases]`, `[project.repository]`, `[project.revision]`, and `[project.environment]`
- `[command.name]` and `[command.path]`

All regular Sigils built-ins remain available, including the environment tool and eager/lazy recursive semantics supplied by the `sigils` library itself.

The pre-1.0 implementation has been preserved in [`arthexis/gway-legacy`](https://github.com/arthexis/gway-legacy). Legacy bundled projects, recipes, shared mutable context, and application-specific dependencies are intentionally not part of this codebase.

See [`PLAN.md`](PLAN.md) for the architecture and implementation sequence. `gway-epaper` is now explicitly scheduled immediately after the Django/Arthexis end-to-end milestone; see [`PLAN-EPAPER.md`](PLAN-EPAPER.md) for that roadmap extension.

## Development

GWAY currently contains the generation-1 skeleton only.

```bash
python -m pip install -e '.[dev]'
python -m gway --help
gway --help
pytest
```

The package and executable remain named `gway`; development continues on the `1.0.0` version line.
