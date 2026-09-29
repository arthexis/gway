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
gway -R ./ops watch
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
| `arthexis/*` | maintained recipes | Arthexis setup, exposure, cleanup, and interactive operations |
| `bootstrap/watchtower` | maintained recipe | bootstrap/expose Watchtower infrastructure |
| `ci` | first-class recipe | repository/project CI entry point |
| `mcp/*` | recipes + capability package | local/remote MCP serving and acceptance |
| `odoo` | capability package | lazy Odoo operation ingestion |
| `remote/browser` | maintained recipe | remote browser route topology |
| `watch` | first-class recipe | bounded read-only node snapshot |
| `web/app` | first-class recipe + capability package | generic maintained web application |
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
- `arthexis/interactive`
- `arthexis/setup`
- `bootstrap/watchtower`
- `ci`
- `mcp/accept`
- `mcp/local`
- `mcp/serve`
- `mcp/server`
- `remote/browser`
- `watch`
- `web/app`
- `web/expose/cleanup-http`
- `web/expose/cleanup`
- `web/expose/dns-http`
- `web/expose/expose`
- `web/expose/godaddy-setup`
- `web/expose/http`
- `web/expose/https`
- `web/remote/cleanup-http`
- `web/remote/expose`
- `web/remote/http`
- `web/remote/https`
- `wire/enroll`
- `wire/watchtower`

## Operation and capability reference

### `watch`

`watch` is the reference first-class sampler operation.

```console
gway watch
gway watch --scope operations-basic
gway watch --only node,services
gway watch --except errors,wire
gway watch --since "10 minutes ago"
gway watch --errors
gway watch --changed --cursor <cursor>
gway -t watch
```

It is strictly non-mutating and safe under query/no-mutate execution.

Its visible section set is reduced by caller authority, then optional
`--scope` attenuation, then `--only`/`--except`, then behavioral filters.
Unauthorized sections are omitted; authorized-but-unsupported capabilities may
appear as `unavailable`; blocked/error sections remain bounded structured
observations.

The stable aggregate uses the following section names when applicable:

- `node`
- `health`
- `services`
- `deploy`
- `release`
- `queue`
- `wire`
- `errors`
- `changed_at`
- `cursor`

Every successful snapshot returns an opaque versioned cursor. Incremental
comparison is stateless:

```console
gway watch --changed --cursor <previous-cursor>
```

Sections lost because later authority is narrower are not exposed as removals.

CLI output uses the generic structured renderer. `-j/--json` returns
machine-readable JSON, while MCP/remote receive structured results directly.
The recipe does not branch on transport.

`-t/--timed` is also generic: route discovery, recipe load/parse/execute, each
nested operation, and the overall first-class operation can be measured without
changing the watch result.

### `ci`

`ci` is a first-class maintained directory recipe at
`sampler/ci/__main__.rx`.

```console
gway ci
```

It is intentionally project-oriented: Gway supplies the common execution and
failure semantics, while a project may shadow the sampler fallback with its own
root `ci.rx` or equivalent first-class operation.

See [ci.md](ci.md) for the CI-specific design.

### `mcp/*`

The MCP sampler family owns maintained MCP launch/acceptance composition.

Common entries:

```console
gway mcp local
gway mcp serve
gway recipe mcp/accept
```

`mcp/server` remains a maintained compatibility path used by the shared server
implementation. `mcp/serve` is the preferred semantic serving entry point.

The Python capability package supplies the FastMCP transport and authorization
bridge, while ordinary Gway command execution remains in the parent Gateway.
Read-only MCP `query` uses `mutate=False`; the generic `gway` tool is the
mutation-capable surface.

See [MCP.md](MCP.md) and [REMOTE.md](REMOTE.md).

### `wire/*`

The Wire family combines maintained recipes with a lazy Python capability
package.

Recipes:

- `wire/enroll` — run/configure the enrollment path.
- `wire/watchtower` — converge Watchtower as the central Wire server.

The package also exposes ordinary Wire read/mutation operations such as status,
check, and device inventory according to the active role and authority.

Templates such as `client.conf` and `interface.conf` are implementation
assets, not public recipes.

### `web/app`

`web/app` is a maintained first-class directory recipe backed by a Python
capability package. It provides the generic web application/server surface used
by maintained remote/browser composition.

```console
gway web app
```

Its internal adapter, schema, presentation, server, and application modules are
supporting implementation files rather than standalone sampler operations.

### `web/expose/*`

Maintained web exposure recipes include:

- `web/expose/http`
- `web/expose/https`
- `web/expose/expose`
- `web/expose/cleanup`
- `web/expose/cleanup-http`
- `web/expose/dns-http`
- `web/expose/godaddy-setup`

They compose generic process/render/filesystem/DNS operations to establish and
remove Nginx/ACME/TLS exposure. Nginx configuration files in the same directory
are templates, not public operations.

Provider credentials are resolved through semantic bindings; recipes should not
embed credentials.

See [RECIPES.md](RECIPES.md) for DNS credential semantics.

### `web/remote/*`

Maintained remote-service exposure recipes include:

- `web/remote/http`
- `web/remote/https`
- `web/remote/expose`
- `web/remote/cleanup-http`

They own the HTTP/HTTPS reverse-proxy topology used for the remote service.
Templates are internal assets.

See [REMOTE.md](REMOTE.md).

### `remote/browser`

`remote/browser` owns the maintained browser route topology and static/template
composition for remote account linking, consent, privacy, and connection
management.

The actual browser behavior lives in Python controllers; the recipe declares
the route/application composition.

### `arthexis/*`

The Arthexis sampler family contains maintained deployment compositions:

- `arthexis/setup`
- `arthexis/expose`
- `arthexis/cleanup`
- `arthexis/dns-expose`
- `arthexis/dns-cleanup`
- `arthexis/interactive`

These are product-oriented maintained recipes that compose generic Gway
operations. Arthexis domain behavior remains in the Arthexis product rather
than being duplicated inside Gway.

### `bootstrap/watchtower`

`bootstrap/watchtower` supplies the maintained Watchtower bootstrap/exposure
composition and associated Nginx templates/bootstrap shell asset.

The shell/config files are deployment assets rather than first-class operations.

### `odoo`

The Odoo directory is a lazy Python capability package rather than an `.rx`
recipe family. It exposes Odoo-specific operations only when semantic resolution
needs that capability, keeping ordinary startup/discovery lightweight.

## Query, mutation, topics, and scopes

Sampler-backed first-class operations use the same metadata and enforcement as
Python-backed operations.

- A companion `mutate=False` contract marks a recipe operation read-only.
- Query/no-mutate remains a monotonic ceiling; a read-only recipe cannot invoke
  a mutating child successfully.
- Remote authorization applies to the first-class operation and to protected
  nested component operations where the composition explicitly re-enters caller
  authority.
- Sampler operations use ordinary semantic subjects/topics. There is no special
  sampler-only topic grammar.
- A directory name may act as the bare subject and as a semantic namespace for
  child operations.

Use `gway help <operation>`, `gway describe ...`, and source inspection for
the exact runtime metadata of a specific operation.

## Authoring a maintained sampler operation

### Choose the right layer

Put work in **core Python** when it is a reusable primitive, algorithm, protocol
implementation, complex state machine, or framework mechanism.

Put work in the **sampler** when the sequence/composition itself is useful
operational documentation and existing semantic operations already provide the
right primitives.

Put work in a **product/project** when it is domain-specific policy or behavior
that should not become part of generic Gway.

### First-class recipe layout

For a single top-level operation:

```text
sampler/example.rx
sampler/example.py
```

For an operation family:

```text
sampler/example/
    __main__.rx
    __main__.py
    child.rx
```

Only root recipes and immediate directory children of a first-class directory
entry are automatically published through the operation-route mechanism.
Deeper recipes remain explicit/internal unless separately exposed.

### Companion public contract

A companion `__main__` may declare the public interface:

```python
def __main__(scope=None, *, mutate=False):
    """Describe the first-class recipe operation."""
```

Discovery reads this contract statically. The function is not the recipe
implementation and is not called instead of the `.rx` body.

Leading comments in the recipe provide fallback documentation. A reserved
static `__help__` companion value may provide structured help topics. Other
dunder hooks are reserved and are not published as child operations.

### Tests expected for new public sampler entries

A maintained public sampler operation should normally cover:

- discovery/public naming;
- root precedence/collision behavior when relevant;
- help/describe metadata;
- mutation/query classification;
- argument binding;
- structured result shape;
- chaining/context behavior where relevant;
- remote/MCP exposure for server-trusted routes;
- security boundaries and bounded failure behavior;
- recipe/static validation.

Update this document's inventory when adding or removing a maintained recipe.
The repository test suite verifies that every name returned by
`gway.sampler.recipes()` appears in this reference.

## Timing and future `.qz` optimization

`-t/--timed` is the generic optimization/diagnostic surface.

For a first-class recipe it can expose:

```text
[timed] route sampler discovery ...
[timed] recipe watch load ...
[timed] recipe watch parse ...
[timed] recipe watch execute ...
[timed] operation node ...
[timed] operation watch ...
```

A future `.qz` implementation may reduce discovery/loading/parsing or execution
cost, but it must remain observationally equivalent to the existing operation:

- same public name;
- same arguments/help/topics;
- same scope and mutation metadata;
- same structured result semantics;
- same CLI and MCP behavior.

Performance thresholds are intentionally not enforced in ordinary CI because
hosted runner timing is not stable enough for reliable absolute limits.
