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

The pre-1.0 implementation has been preserved in [`arthexis/gway-legacy`](https://github.com/arthexis/gway-legacy). Legacy bundled projects, recipes, sigils, shared mutable context, and application-specific dependencies are intentionally not part of this codebase.

See [`PLAN.md`](PLAN.md) for the architecture and implementation sequence. `gway-epaper` is now explicitly scheduled immediately after the Django/Arthexis end-to-end milestone; see [`PLAN-EPAPER.md`](PLAN-EPAPER.md) for that roadmap extension.

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

## Development

GWAY currently contains the generation-1 skeleton only.

```bash
python -m pip install -e '.[dev]'
python -m gway --help
gway --help
pytest
```

The package and executable remain named `gway`; development continues on the `1.0.0` version line.
