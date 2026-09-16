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

## Precedence

Semantic values use one precedence contract:

```text
runtime/context value
→ GWAY_<NORMALIZED_SEMANTIC_NAME>
→ gway.toml [variables] value
→ inline Sigil fallback
→ unresolved Sigil behavior
```

Explicit command-line arguments remain outside this chain and continue to override function defaults in the normal dispatcher path.

Unprefixed process environment variables are not implicit semantic-variable overrides. For example, `ARTHEXIS_DATA` does not override `[arthexis.data]`; use `GWAY_ARTHEXIS_DATA` instead.

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

This convention is intended to be shared by CLI commands, recipes, function-default Sigils, managed services, and API/MCP integrations so callers do not need per-project environment-variable plumbing.
