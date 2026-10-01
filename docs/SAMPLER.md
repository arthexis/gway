# Maintained sampler

The sampler is Gway's maintained library of replaceable operational compositions
and capability packages. It lives in the repository's top-level `sampler/`
directory and is installed with the package.

This document is the authoritative reference for the maintained sampler itself.
For the recipe language, execution model, rollback rules, and companion Python
mechanics, see [RECIPES.md](RECIPES.md).

## What belongs in the sampler

Gway deliberately separates several implementation layers:

- **Core Python operations** provide reusable semantic primitives and framework
  behavior.
- **Sampler recipes** compose those primitives into maintained operational
  workflows.
- **Sampler capability packages** lazily expose Python-backed operation
  families when a semantic command needs them.
- **Products/projects** own domain-specific behavior that should not become
  generic Gway policy.
- **Project-local recipes/operations** may override maintained fallback behavior
  for a particular project.

Sampler implementations are intentionally replaceable. A public operation may
be backed by Python, `.rx`, or a future compiled/cache representation such as
`.qz` without changing its public Gway contract.

A sampler capability does not need a recipe. A directory containing
`__init__.py` is a normal Python capability package and may expose a
`register(runtime)` hook. The sampler fallback loads that package only when its
semantic route is needed; the `sampler/` filesystem prefix is not part of the
public operation name. Internal Python modules under the package may be split by
domain and composed by `__init__.py` without becoming separate recipes.

For example, `sampler/github/` is a plain Python capability package. Its normal
sampler discovery publishes `github.*` operations; `Gateway` contains no
GitHub-specific ingestion hook.

## Operation roots and precedence

Gway resolves ordinary registered/project-local operations before consulting
fallback operation routes.

The fallback order is:

1. the established project-local/root operation surface;
2. explicit local CLI operation roots supplied with `-R/--root`, from left to
   right;
3. the maintained sampler.

Examples:

```console
gway -R ./ops survey
gway -R ./primary -R ./secondary deploy
```

The first explicit root wins over later explicit roots. An explicit root may
shadow a maintained sampler operation, but it does not supersede an already
selected project-local/registered operation.

CLI operation roots are:

- request-local and non-persistent;
- normalized local filesystem directories;
- resolved relative to the invoking process working directory;
- not URLs or remote references;
- not caller-configurable through MCP/remote.

Remote callers may invoke operations already exposed by server-trusted roots,
but cannot cause the server to discover arbitrary caller-selected filesystem
roots.

Ambiguous duplicate public registrations at the same effective route level are
rejected rather than silently selected.

## First-class sampler operations

An eligible root recipe participates in ordinary operation discovery.

Direct form:

```text
sampler/example.rx
sampler/example.py
```

Directory entry form:

```text
sampler/example/
    __main__.rx
    __main__.py
    child.rx
```

The directory form exposes:

```console
gway example
gway example child
```

The companion Python `__main__` callable is the public contract only. Its
signature/docstring/defaults and mutation metadata are projected onto the recipe
operation, while execution still runs `__main__.rx`.

Reserved dunder companion functions are framework hooks, not user-visible child
operations.

## Sampler index

The maintained sampler currently contains these public families.

| Family | Kind | Primary use |
| --- | --- | --- |
| `arthexis/*` | maintained recipes | Arthexis setup, exposure, and cleanup operations |
| `bootstrap/watchtower` | maintained recipe | bootstrap/expose Watchtower infrastructure |
| `ci` | first-class recipe | repository/project CI entry point |
| `github` | capability package | lazy GitHub source, collaboration, Actions, and CI-check operations |
| `mcp/*` | recipes + capability package | local/remote MCP serving and acceptance |
| `network/capture` | maintained recipe | bounded network capture composition |
| `odoo` | capability package | lazy Odoo operation ingestion |
| `remote/browser` | maintained recipe | remote browser route topology |
| `survey` | first-class recipe | bounded read-only node snapshot |
| `web/app` | first-class recipe + capability package | generic maintained web application |
| `web/expose` | maintained recipe | generic web exposure entry point |
| `web/expose/*` | maintained recipes | HTTP/HTTPS exposure and cleanup |
| `web/remote/*` | maintained recipes | remote service HTTP/HTTPS exposure |
| `wire/*` | recipes + capability package | Wire enrollment, server convergence, and Wire operations |

### Complete maintained recipe inventory

The names below match `gway.sampler.recipes()` and may be passed to the
maintained recipe resolver where appropriate.

- `arthexis/cleanup`
- `arthexis/dns-cleanup`
- `arthexis/dns-expose`
- `arthexis/expose`
- `arthexis/setup`
- `bootstrap/watchtower`
- `ci`
- `mcp/accept`
- `mcp/local`
- `mcp/serve`
- `mcp/server`
- `network/capture`
- `remote/browser`
- `survey`
- `web/app`
- `web/expose`
- `web/expose/cleanup-http`
- `web/expose/cleanup`
- `web/expose/dns-http`
- `web/expose/expose`
- `web/expose/http`
- `web/expose/https`
- `web/remote/cleanup-http`
- `web/remote/expose`
- `web/remote/http`
- `web/remote/https`
- `wire/enroll`
- `wire/watchtower`

## Operation and capability reference

### `survey`

`survey` is the reference first-class sampler operation.

```console
gway survey
gway survey --scope operations-basic
gway survey --only node,services
gway survey --except errors,wire
gway survey --since "10 minutes ago"
gway survey --problems
gway survey --changed --cursor <cursor>
gway -t survey
```

It is strictly non-mutating and safe under query/no-mutate execution.

Its visible section set is reduced by caller authority, then optional
`--scope` attenuation, then `--only`/`--except`, then behavioral filters.
Unauthorized sections are omitted; authorized-but-unsupported capabilities may
appear as `unavailable`; blocked/error sections remain bounded structured
observations.
