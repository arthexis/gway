# GWAY Projects

GWAY treats standard Python project metadata as the primary project contract.
This document describes the project-level information GWAY currently discovers
or reads from a project checkout.

## Project discovery

For a local checkout, GWAY searches from the current directory upward and uses
the nearest `pyproject.toml`. Its parent directory is the project root.

Managed installations are discovered from GWAY's installation registry. A
managed installation is considered valid only when its recorded installation
path is the expected managed project directory and that directory still contains
a `pyproject.toml`.

GWAY does not require a separate project manifest.

## Standard Python metadata

### `[project].name`

```toml
[project]
name = "example"
```

The project name is GWAY's project identity.

GWAY uses it when:

- bootstrapping a local project;
- installing and identifying managed projects;
- qualifying project-owned operations;
- assigning ownership to Sous Chef jobs.

A non-empty project name is required for installation. Sous Chef declarations
also require a valid project name.

### `[project.scripts]`

```toml
[project.scripts]
example = "example:main"
status = "example.status:show"
```

GWAY exposes standard Python console-script declarations as project operations.

Each value must be a `module:callable` target. GWAY validates both the command
name and target before exposing it. Installed projects are qualified by project
identity; a bare script alias is added only when that script name has a unique
owner.

No GWAY-specific duplicate of `[project.scripts]` is needed.

## GWAY-specific metadata

GWAY-specific configuration lives under `[tool.gway]` and is used only for
behavior that standard Python project metadata does not express.

### `[tool.gway.variables]`

```toml
[tool.gway.variables]
site = "MTY"
role = "Watchtower"
```

Every key/value pair in this table becomes project-provided semantic context.
GWAY loads these values as the `pyproject` source during local project
bootstrap.

The table is optional. If present, it must be a TOML table.

### `[[tool.gway.guide]]`

Projects can publish explicit task guidance for the read-only `guide` operation:

```toml
[[tool.gway.guide]]
tasks = ["check production logs", "inspect logs"]
command = "log read --all"
reason = "Use the maintained log reader for this deployment."
roles = ["watchtower"]
```

Each declaration requires `tasks`, `reason`, and one recommendation target.

For a GWAY recommendation:

- `command`: the preferred GWAY command;
- optional `roles`: node/project roles for which the recommendation applies.

For an external capability recommendation:

```toml
[[tool.gway.guide]]
tasks = ["modify source", "review pull request", "check ci"]
use = "external"
capability = "source-control"
reason = "The repository is the canonical development surface."
```

External rules require `use = "external"` plus a non-empty generic
`capability` class. They must not also define `command`. Capability names are
client-independent (for example `source-control`, `web-search`,
`file-editor`, `browser`, or `database-admin`).

`guide <task>` ranks these explicit declarations first. When the project exposes
a semantic `role` (for example under `[tool.gway.variables]`), declarations with
matching `roles` are eligible and outrank otherwise equivalent generic rules.
Role-specific declarations for another role are excluded.

It returns structured recommendations with the command, reason, project source, and
the configured task phrase that matched. The command is only a recommendation:
`guide` does not execute it or grant authorization to use it. Guide results are
result-only mappings and do not promote their metadata into semantic context.

After explicit and role-aware declarations, `guide` may fall back to metadata from
operations currently registered in the live Gateway. This lexical fallback uses the
canonical command spelling and compact operation summary, remains lower priority than
project declarations, and is filtered by the caller's active authorization when one
exists. It does not execute the recommended operation.

After live operations, `guide` can also recommend maintained sampler recipes by
their semantic recipe path. Recipe recommendations use the safe
`recipe <sampler-name>` operation rather than exposing direct filesystem paths.
Under constrained remote authorization, recipes are only advertised when the
caller is authorized for the `recipe` operation.

External capability declarations participate in the same explicit task ranking and
role filtering as GWAY declarations, but appear in the result's `external` array.
They are recommendations only and are independent of GWAY execution authorization.

The full role-aware `node` execution surface, broader docstring fallbacks, and
documentation fallbacks remain separate later layers of the guide design.

### `[tool.gway.sous-chef.<job>]`

Sous Chef jobs are project-owned recipe jobs:

```toml
[tool.gway.sous-chef.cleanup]
recipe = "recipes/cleanup.rx"
every = "1h"
watch = "state/"
down = "service stop"
timeout = "10m"
```

The job name is the final table component—in this example, `cleanup`. GWAY
currently recognizes exactly these attributes:

| Attribute | Required | Meaning |
| --- | --- | --- |
| `recipe` | yes | Recipe path to execute. Relative paths are resolved from the project root. |
| `every` | no | Periodic trigger interval. Accepts a positive number of seconds or a compact duration ending in `s`, `m`, `h`, or `d`. |
| `watch` | no | Filesystem path trigger. Relative paths are resolved from the project root. |
| `down` | no | Non-empty target string used by the down trigger. |
| `timeout` | no | Job timeout, using the same duration syntax as `every`. Defaults to 15 minutes. |

Unknown fields in a Sous Chef job are rejected.

A project may declare multiple jobs:

```toml
[tool.gway.sous-chef.cleanup]
recipe = "recipes/cleanup.rx"
every = "1h"

[tool.gway.sous-chef.health]
recipe = "recipes/health.rx"
every = "5m"
timeout = "30s"
```

## Filesystem conventions GWAY also inspects

Not every project behavior comes from a TOML attribute.

GWAY also looks for conventional Python packages containing `__main__.py`
under either the project root or a conventional `src/` directory. Those
package entry points can become launchable GWAY operations. This is filesystem
discovery, not a `pyproject.toml` field.

Similarly, the existence and location of `pyproject.toml` define the project
root used to resolve project-relative paths.

## What GWAY does not currently read as project behavior

Other standard `[project]` metadata remains valid Python packaging metadata,
but GWAY does not currently use fields such as `version`, `description`,
`authors`, or `urls` to define its runtime project behavior.

Prefer standard Python metadata whenever it already expresses the concept.
Add new `[tool.gway]` keys only when a GWAY-specific behavior genuinely needs
project-level configuration.
