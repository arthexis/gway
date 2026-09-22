# MCP

GWAY exposes Model Context Protocol (MCP) as a transport for native GWAY commands.
FastMCP does not define a parallel command language and ordinary GWAY operations do
not need MCP-specific wrappers or decorators.

## Architecture

The public MCP surface is intentionally small:

```text
gway(command: str)
```

The command string is forwarded unchanged to the authoritative parent `Gateway`.
The parent remains responsible for tokenization, semantic resolution, sigils,
pipelines, recipes, binding, adapters, authorization, and execution.

```text
MCP client
    |
    | gway(command="...")
    v
FastMCP transport
    |
    v
managed companion / private callback
    |
    v
authoritative parent Gateway
    |
    +-- resolve canonical operation
    +-- authorize it
    +-- bind values
    +-- invoke it
    +-- repeat for the next stage
```

Authorization is therefore checked for every resolved operation in a multi-stage
command. Tool visibility is not a security boundary.

The FastMCP implementation lives in `sampler/mcp`. The core `gway` package is
transport-independent.

## Authorization and trusted recipes

Remote authorization is expressed with canonical GWAY operation identities.
Aliases and CLI spelling do not create alternate permissions.

A trusted recipe is a capability boundary. If a caller may invoke the recipe, its
internal implementation operations may run under the recipe's trusted capability
for the duration of that recipe. Direct remote invocation of those internal
operations still requires explicit permission.

Authenticated MCP execution explicitly drops any trusted capability inherited from
the MCP transport recipe before running the remote command. The bearer token's
authority is therefore the effective remote authority.

Request-local results and semantic context created by authorized execution remain
available to later stages and sigils in that request. Ambient host state is not
implicitly granted.

## Environment access

Environment access is denied by default for externally authorized execution.

Scopes contain `operations` and `environment` as peer grant sets. Exact variable
names may be granted, and `__all__` is the explicit full-environment grant.

Environment lookup through sigils follows the ordinary `env` operation, so it is
subject to both operation authorization and the environment-name allowlist.
`envs` only exposes names permitted by the current authority.

Unauthorized environment values must not enter remote results or authorization
errors.

## Named scopes

Scopes are stored in the versioned SQLite security registry. For example:

```text
gway security scope create logs-read
gway security scope set logs-read log.sources log.read log.tail log.search
gway security scope show logs-read
gway security scope list
```

The canonical read-only logging scope is:

```toml
[scopes.logs-read]
operations = ["log.sources", "log.read", "log.tail", "log.search"]
environment = []
```

Declarative TOML may be applied transactionally:

```text
gway security scope apply scopes.toml
```

Applying the same document repeatedly is convergent. Scopes listed in the document
are replaced atomically; unrelated existing scopes are left unchanged.

Export the current registry with:

```text
gway security scope export --to scopes.toml
```

SQLite remains the live authority; TOML is the reviewable import/export surface.

## Opaque bearer tokens

Tokens are GWAY-owned opaque credentials. The plaintext bearer is returned only at
creation time; persistent state stores only its public lookup ID and verifier hash.

```text
gway security token create observer logs-read
gway security token show observer
gway security token list
gway security token disable observer
gway security token enable observer
gway security token delete observer
```

A token may have an optional timezone-aware ISO-8601 expiry:

```text
gway security token create observer logs-read \
    --expires 2026-10-01T00:00:00+00:00
```

Malformed, unknown, wrong-secret, disabled, and expired credentials all fail with
the same external authentication error. Scope bindings are resolved when the token
is authenticated, so changing a named scope changes the token's effective authority
without reissuing it.

## stdio and Streamable HTTP

The maintained companion supports stdio for local/client-managed sessions and
Streamable HTTP for a long-running service.

HTTP defaults to loopback:

```text
127.0.0.1:8000/mcp
```

Remote HTTP calls require:

```text
Authorization: Bearer <opaque-token>
```

The bearer is verified by the authoritative parent process. The FastMCP child does
not construct or trust caller-supplied permission sets.

For network exposure, keep the MCP service loopback-bound and place an appropriate
TLS reverse proxy or tunnel in front of it rather than adding certificate or proxy
management to the MCP sampler.

## Service deployment

The maintained server is the ordinary recipe:

```text
sampler/mcp/server.rx
```

It installs FastMCP through recipe-managed `require fastmcp` and runs the HTTP
server. GWAY's generic service layer owns supervision.

A process-backed deployment can be installed with the generic service controller,
using the stable service name `mcp-server`. Systemd deployment uses the same
service model and generic systemd renderer. The MCP implementation itself contains
no systemd commands, pidfile handling, daemonization, or restart loop.

Conceptually:

```text
service install --backend process --name mcp-server -- <server.rx>
service start --name mcp-server -- <server.rx>
service status --name mcp-server -- <server.rx>
service restart --name mcp-server -- <server.rx>
service stop --name mcp-server -- <server.rx>
```

The exact recipe path depends on the installed sampler location.

## Logging example

Logging is an ordinary GWAY API, not a logging-specific MCP protocol. A client with
the `logs-read` scope can call:

```text
gway(command="log sources")
gway(command="log tail arthexis --limit 20")
gway(command="log read arthexis/web --since '10 minutes ago'")
gway(command="log search timeout arthexis")
```

The same `gway(command)` tool is used for every other authorized GWAY command.

## Security boundaries

The transport maintains two separate credentials:

- the user-facing opaque bearer token used for GWAY authentication;
- an ephemeral private callback-relay token used only between the managed FastMCP
  process and its parent Gateway.

They are not interchangeable. Raw bearer material must not be logged or persisted.

No wildcard operation scope is created implicitly, no new operation becomes
authorized merely because it is later ingested, and no environment permission is
granted unless explicitly present in a scope.

## Deferred features

The current MCP implementation intentionally does not add OAuth, generated
per-operation MCP tools, wildcard scopes, wildcard environment grants, dedicated
logging routes, background MCP tasks, MCP Apps/UI, OpenAPI conversion, remote
plugin loading, or a second transport abstraction around FastMCP.
