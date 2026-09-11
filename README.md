# GWAY

GWAY is a lightweight project manager, command dispatcher, and composition layer for the Arthexis/GWAY ecosystem.

It discovers and manages projects from GitHub, installs them into isolated environments, and exposes their commands through a common interface:

```text
gway <project> <command> [arguments]
```

Install the released package with:

```bash
python -m pip install gway
```

## Managed projects

Projects own their command surfaces. GWAY discovers commands through adapters instead of embedding project-specific behavior in core. Python function introspection and Django management commands are the primary adapter surfaces.

Typical lifecycle commands include:

```bash
gway list
gway search
gway install wireguard
gway upgrade wireguard
gway info wireguard
gway path wireguard
gway remove wireguard
```

Installed projects become CLI namespaces:

```bash
gway wireguard status
gway arthexis check
```

## Python API

GWAY provides a first-class importable facade:

```python
from gway import gway as gw

gw.projects()
gw.project("wireguard")
```

`from gway import gw` remains available as a compatibility alias. Dynamic managed-command calls such as `gw.wireguard.status()` are part of the intended API contract but are not implemented by the facade yet.

See [`docs/PYTHON_API.md`](docs/PYTHON_API.md) for the current surface and required command-dispatch contract.

## Sigils and composition

`gway-sigils` is GWAY's single runtime dependency and provides the value-expression language. Installing GWAY installs a compatible Sigils release automatically. The GWAY-facing runtime alias remains `sigils`:

```bash
gway install sigils
```

Project names and command paths remain deterministic while argument values may resolve Sigils. GWAY provides eager and lazy context including `cwd`, `home`, GWAY paths, project metadata, command metadata, adapter-provided protected namespaces, and invocation-local chain context.

GWAY can also compose stages with a standalone `-`:

```text
gway producer - consumer
gway % Hello [name] - uppercase
gway [name] is online - uppercase
```

See [`docs/CHAINING.md`](docs/CHAINING.md) for transfer rules, selectors, solve stages, escapes, and chain context.

## System installation

GWAY can be installed or upgraded as a system command without changing the operating system's default Python:

```bash
curl -fsSL https://raw.githubusercontent.com/arthexis/gway/main/install.sh | sudo bash
```

The bootstrap installer selects a supported Python, installs GWAY under `/opt/gway/venv`, maintains system state under `/etc/gway` and `/var/lib/gway`, and exposes `/usr/local/bin/gway`. It preserves an existing unmanaged command before replacement and can be rerun to upgrade the managed installation.

Validate prerequisites without changing the machine:

```bash
curl -fsSL https://raw.githubusercontent.com/arthexis/gway/main/install.sh -o /tmp/gway-install.sh
bash /tmp/gway-install.sh --check
```

## Upgrading

Upgrade one managed project:

```bash
sudo gway upgrade wireguard
```

A bare upgrade upgrades GWAY itself and then managed projects:

```bash
sudo gway upgrade
```

Other useful forms are:

```bash
sudo gway upgrade --self
sudo gway upgrade --all
sudo gway upgrade --all --no-self
sudo gway upgrade wireguard --force
```

Managed upgrades validate the trusted repository and branch, refresh the isolated environment, re-read `gway.toml`, and record the new revision. `--force` is an explicit appliance-recovery path that discards local managed-checkout changes after validating the registered upstream.

## Documentation

The repository root is kept for files that are important at checkout/package level. Detailed design and product documentation lives under `docs/`:

- [`docs/PLAN.md`](docs/PLAN.md) — current architecture and roadmap
- [`docs/CHAINING.md`](docs/CHAINING.md) — command chaining and solve grammar
- [`docs/PYTHON_API.md`](docs/PYTHON_API.md) — importable API contract
- [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) — cross-cutting requirements

The pre-1.0 implementation is preserved in [`arthexis/gway-legacy`](https://github.com/arthexis/gway-legacy). Legacy bundled projects, recipes, shared mutable context, and application-specific dependencies are intentionally not part of this codebase.

## Development

```bash
python -m pip install -e '.[dev]'
python -m gway --help
gway --help
pytest
```

Repository-specific contributor rules are in [`AGENTS.md`](AGENTS.md).
