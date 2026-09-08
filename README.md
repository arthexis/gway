# GWAY

GWAY is a lightweight project manager and command dispatcher for the Arthexis/GWAY ecosystem.

The 1.x generation discovers and manages projects from GitHub and exposes each project's commands through a common `gway <project> <command>` interface. Framework-specific command discovery is provided by adapters, including Python function introspection and Django management commands.

Install the released package with:

```bash
python -m pip install gway
```

GWAY also keeps a first-class Python API. The intended stable import is:

```python
from gway import gway as gw

# Mirrors the CLI namespace once the relevant managed projects are installed.
gw.wireguard.status()
gw.arthexis.check()
```

`from gway import gw` remains available as a compatibility alias. The Python facade uses the same registry, adapter, dispatcher, and runner as the CLI rather than bypassing managed project isolation.

## Sigils on the CLI

`gway-sigils` is GWAY's single runtime dependency and provides the `sigils` Python package used as part of the command-value language. Project names and command paths stay literal for predictable routing; argument values are interpolated before adapter parsing.

Because Sigils is a required GWAY runtime component, installing GWAY already installs it into the same Python environment. The short GWAY-facing name remains `sigils`, so this is an idempotent runtime install/verification command rather than a second managed-project checkout:

```bash
gway install sigils
# installed sigils    gway-sigils@0.4.4
```

The PyPI distribution name `gway-sigils` is therefore an implementation/distribution detail; users do not need to type the `gway-` prefix through GWAY. The command refers to the environment that owns the `gway` executable: a global GWAY installation gives Sigils the same global scope, while virtualenv or pipx installations remain scoped to that environment.

```bash
gway web build --output "[project.path]/dist"
gway ocpp connect --label "%[cwd]-[project.name]"
```

Managed expressions mirror Sigils call syntax. Dots or whitespace traverse project/command paths, while `:` introduces structured arguments:

```text
gway network ip : wlan0
gway network ip : interface=wlan0
gway demo combine : first : second : mode=fast
gway demo echo := left=right
gway demo shape : a,b,c : values=x,y
```

Each `:` introduces one argument. `name=value` binds a keyword argument, while `:=value` forces a positional argument even when the value contains `=`. Commas inside one argument create a tuple value rather than multiple arguments. Whitespace around `:`, `:=`, `=`, and `,` is ignored.

The fallback grammar is also shared with Sigils: `|` advances on any falsey value, `||` advances only on unresolved/missing values, `None`, or an empty set/frozenset, and `|:literal` / `||:literal` provide terminal literal fallbacks. A trailing colon keeps the left side literal, so `gway health.errors:` returns `health.errors` rather than invoking it.

GWAY-backed Sigils use the same registered command surface, including structured arguments:

```text
[network ip : wlan0]
[network ip : interface=wlan0]
[device memory : percent]
```

Calls are memoized only within one Sigil evaluation scope, keyed by project, command path, positional arguments, and keyword arguments. A new evaluation creates a fresh cache.

`%[...]` expressions are captured eagerly before project-provided lazy context is requested. `[...]` expressions resolve immediately before the selected adapter parses the command arguments.

The built-in GWAY context includes:

- `[cwd]` and `[home]`
- `[gway.config_dir]` and `[gway.data_dir]`
- `[project.name]`, `[project.path]`, `[project.adapter]`, `[project.aliases]`, `[project.repository]`, `[project.revision]`, and `[project.environment]`
- `[command.name]` and `[command.path]`

Adapters may add lazy-only top-level roots through the optional `SigilContextAdapter` capability. Added roots cannot replace GWAY's reserved `cwd`, `home`, `gway`, `project`, or `command` namespaces.

Django projects can configure an explicit provider in `gway.toml`:

```toml
[adapter]
type = "django"
manage = "manage.py"
settings = "config.settings"
sigils = "apps.sigils.gway:context"
```

The provider is imported after `django.setup()` and is called as:

```python
def context(*, project, command_path):
    return {"NODE": ...}
```

It must return a mapping. For model-backed data, prefer `sigils.SafeNamespace` so only explicitly exposed keys may be traversed and resolution cannot fall through to arbitrary attributes, callables, or Sigils tools.

All regular Sigils built-ins remain available outside protected namespaces, including the environment tool and eager/lazy recursive semantics supplied by the `sigils` library itself.

The pre-1.0 implementation has been preserved in [`arthexis/gway-legacy`](https://github.com/arthexis/gway-legacy). Legacy bundled projects, recipes, shared mutable context, and application-specific dependencies are intentionally not part of this codebase.

See [`PLAN.md`](PLAN.md) for the architecture and implementation sequence. `gway-epaper` is now explicitly scheduled immediately after the Django/Arthexis end-to-end milestone; see [`PLAN-EPAPER.md`](PLAN-EPAPER.md) for that roadmap extension.

For a reproducible bridge validation before enabling a real ORM-backed provider, see [`MANUAL-SIGIL-CONTEXT.md`](MANUAL-SIGIL-CONTEXT.md).

## System / appliance installation

GWAY 1.x can be installed or upgraded as a system command without changing the operating system's default `python3`:

```bash
curl -fsSL https://raw.githubusercontent.com/arthexis/gway/main/install.sh | sudo bash
```

The bootstrap installer:

- selects an available Python 3.11 or newer interpreter;
- installs GWAY into `/opt/gway/venv`;
- creates system state under `/etc/gway` and `/var/lib/gway`;
- installs `/usr/local/bin/gway` as the system dispatcher;
- automatically archives an existing unmanaged `/usr/local/bin/gway` as `/usr/local/bin/gway-legacy` before replacement;
- preserves additional differing legacy commands with collision-safe timestamped archive names;
- can be rerun safely to upgrade an existing managed GWAY installation.

Validate prerequisites without changing the machine:

```bash
curl -fsSL https://raw.githubusercontent.com/arthexis/gway/main/install.sh -o /tmp/gway-install.sh
bash /tmp/gway-install.sh --check
```

After installation, managed projects can be installed directly, for example:

```bash
sudo gway install wireguard
sudo gway wireguard --help
```

## Upgrading GWAY and managed projects

GWAY owns the lifecycle of projects installed through `gway install`. Upgrade one managed project with:

```bash
sudo gway upgrade wireguard
```

Upgrade all managed projects while leaving GWAY itself unchanged:

```bash
sudo gway upgrade --all
```

Upgrade only GWAY in the Python environment that owns the current `gway` executable:

```bash
sudo gway upgrade --self
```

A bare upgrade performs both operations in order: GWAY itself first, then every managed project:

```bash
sudo gway upgrade
```

Managed project upgrades normally require a clean checkout whose `origin` still matches the trusted repository recorded by GWAY. Normal upgrades use `git pull --ff-only`, refresh the project's isolated Python environment, re-read `gway.toml`, and record the new revision. Locally registered projects created with `gway register` are not modified by `--all`; naming one explicitly is rejected.

For appliance recovery, `--force` deliberately discards local managed-checkout changes after validating the registered origin and current branch. It fetches the trusted upstream, resets the checkout to `origin/<branch>`, and removes ordinary untracked files/directories; ignored files are preserved. It can target one project or all managed projects:

```bash
sudo gway upgrade wireguard --force
sudo gway upgrade --all --force
sudo gway upgrade --force
```

The last form upgrades GWAY itself normally, then force-resets and upgrades all managed projects.

## Development

```bash
python -m pip install -e '.[dev]'
python -m gway --help
gway --help
pytest
```

The package and executable remain named `gway`; the stable 1.x line starts at version 1.0.0.
