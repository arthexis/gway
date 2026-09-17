# Semantic variables

Gway project variables are semantic configuration names. Declare them in `gway.toml` and reference them through Sigils without teaching each project about deployment-specific environment variable names.

```toml
[variables.arthexis]
data = ".arthexis/data"
```

```text
[arthexis.data]
```

Every semantic variable leaf automatically has a deterministic `GWAY_*` environment fallback. Gway derives the environment name by uppercasing the semantic path, converting non-alphanumeric separators to `_`, collapsing repeated separators, and prefixing `GWAY_`.

```text
arthexis.data       -> GWAY_ARTHEXIS_DATA
arthexis-data       -> GWAY_ARTHEXIS_DATA
arthexis.data.root  -> GWAY_ARTHEXIS_DATA_ROOT
repo.endpoint       -> GWAY_REPO_ENDPOINT
```

This lets a managed deployment override repository defaults without changing the project manifest:

```bash
export GWAY_ARTHEXIS_DATA=/opt/arthexis/var/lib
```

`[arthexis.data]` then resolves to `/opt/arthexis/var/lib`.

## Project-native ENV prefixes

Projects may opt into a native ENV namespace for semantic variables they own:

```toml
[project]
name = "arthexis"
env_prefix = "ARTHEXIS"

[variables.arthexis]
data = ".arthexis/data"
cache = ".arthexis/cache"
```

Because `arthexis.data` is owned by the canonical `arthexis` project namespace, Gway checks the native route before the universal route:

```text
[arthexis.data]

ARTHEXIS_DATA
GWAY_ARTHEXIS_DATA
TOML default
```

The canonical project namespace is stripped exactly once when constructing the native ENV name:

```text
arthexis.data       -> ARTHEXIS_DATA
arthexis.cache.root -> ARTHEXIS_CACHE_ROOT
```

Aliases do not establish ownership, and unrelated namespaces do not inherit the project prefix. For example, an Arthexis manifest containing `repo.endpoint` still resolves that variable through `GWAY_REPO_ENDPOINT`, not `ARTHEXIS_REPO_ENDPOINT`.

`env_prefix` is optional. Projects that omit it keep the universal `GWAY_*` behavior unchanged. Prefixes are normalized to uppercase and must start with a letter, contain only letters, numbers, and underscores, and not end with an underscore.

## Precedence

For a project-owned semantic variable with a native prefix, the full precedence contract is:

```text
runtime/context value
→ project-native environment variable
→ GWAY_<NORMALIZED_SEMANTIC_NAME>
→ gway.toml [variables] value
→ inline Sigil fallback
→ unresolved Sigil behavior
```

For variables without a project-native route, the native step is simply skipped.

Explicit command-line arguments remain outside this chain and continue to override function defaults in the normal dispatcher path.

Arbitrary unprefixed process environment variables are not implicit semantic-variable overrides. Native variables are consulted only when the project explicitly declares `env_prefix` and the semantic path is owned by that project's canonical namespace.

## Nested variables

Use TOML tables to express namespaced semantic variables:

```toml
[variables.server]
host = "127.0.0.1"
port = 8080

[variables.logs]
endpoint = "https://logs.example.com"
```

The corresponding automatic environment fallbacks are:

```text
GWAY_SERVER_HOST
GWAY_SERVER_PORT
GWAY_LOGS_ENDPOINT
```

## Managed services

Managed service command arguments and environment values may reference the same semantic variables. Gway resolves them before rendering the systemd unit, so the service definition does not need deployment-specific environment lookup logic.

```toml
[variables.logs]
source = "~/.local/state/gway/runs"

[services.logs]
command = [
    "{python}",
    "-m",
    "gway_web.log_service",
    "--source",
    "[logs.source]",
]

[services.logs.environment]
LOG_SOURCE = "[logs.source]"
```

A deployment can override both references without changing the manifest:

```bash
export GWAY_LOGS_SOURCE=/opt/gway/runs
```

Service Sigils use the same precedence contract as other semantic variables. Only the selected service topology is resolved, so an unrelated service does not block an explicit service selection. Unlike ordinary noninteractive solving, unresolved service Sigils fail closed before a unit is written or replaced; generated systemd units therefore contain concrete values rather than unresolved Sigil expressions.

This convention is intended to be shared by CLI commands, recipes, function-default Sigils, managed services, and API/MCP integrations so callers do not need per-project environment-variable plumbing.
