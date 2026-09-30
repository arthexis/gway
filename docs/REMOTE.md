# Remote access service

G-Way packages the shared OAuth and account server as the built-in
`remote.serve` launchable. Its service preset has the stable identity
`remote-auth`, so it uses the same generic lifecycle as other G-Way services.

The default internal listener is:

```text
127.0.0.1:8001
```

and the default public OAuth origin is:

```text
https://remote.arthexis.com
```

The public origin is metadata only. The service remains loopback-bound until a
separate reverse proxy exposes the public routes.

## Service lifecycle

A systemd deployment uses the ordinary service controller:

```text
gway service install --backend systemd remote serve

gway service start remote serve
gway service status remote serve
gway service restart remote serve
gway service stop remote serve
```

Gway-owned cache/data locations are semantic configuration, not service
environment plumbing. A deployment that needs a shared cache location should
configure `cache_dir` semantically, for example in the project's
`pyproject.toml`:

```toml
[tool.gway.variables]
cache_dir = "/var/lib/gway/cache"
```

Physical environment aliases such as `GWAY_CACHE_DIR` remain compatibility
bindings. When Gway installs its own Remote service, it persists the already
resolved cache root into the service environment so the child Gateway reopens
the same durable state even when systemd runs it under a different user or
without the installer's environment. User-supplied service `--environment`
remains reserved for literal environment contracts of launched external
programs.

OAuth links, grants, access tokens, refresh tokens, and named Gway security
policy live under the Gateway-selected cache root at:

```text
<cache_dir>/security/state.sqlite
```

That database is outside replaceable application code and outside the generated
systemd unit. Reinstalling the service or upgrading Gway therefore does not
reissue or discard OAuth state.

Credential state is inspectable through the same security command surface. Bare
plural namespaces default to their singular `list` operation when no explicit
plural operation exists:

```text
gway security tokens
gway security oauth clients
gway security oauth links
gway security oauth grants
gway security oauth tokens
```

OAuth grant scopes can be managed without recreating the connection:

```text
gway security oauth grant show <grant-id>
gway security oauth grant bind <grant-id> operator-read
gway security oauth grant unbind <grant-id> operator-read
gway security oauth grant set <grant-id> logs-read operator-read
```

A grant can never exceed the scopes bound to its linked native Gway token.

Native and OAuth token listings include `last_used_at` when a credential has
successfully authenticated. OAuth access also counts as use of its linked native
security token because that token remains the effective policy ceiling. Usage
telemetry is kept separately from the versioned authorization database so it
cannot make an older Gway runtime reject the security schema during rollback.

The OAuth token listing exposes only safe metadata and public ids; bearer
secrets remain one-time material and are never persisted in plaintext.
`security oauth token clear` revokes all issued OAuth access and refresh
credentials while preserving clients, links, and grants. `security token clear`
deletes every native Gway security token and therefore intentionally cascades
through OAuth links, grants, and issued credentials tied to those tokens while
leaving scopes and OAuth client registrations intact.

Remote/MCP configuration follows the same topic hierarchy as other semantic
values. With active topics `remote` and `mcp`, a subject such as
`endpoint` may resolve through:

```text
remote.mcp.endpoint
mcp.remote.endpoint
mcp.endpoint
remote.endpoint
endpoint
```

This is the generic topic algorithm, not a Remote-specific resolver.

For another deployment origin or protected-resource path, pass the normal
`remote serve` arguments through service management, for example:

```text
gway service install --backend systemd remote serve \
  --public-origin https://remote.example.com \
  --resource-path /mcp
```

The remote server itself contains no systemd, pidfile, daemonization, or reverse
proxy logic. G-Way service backends own supervision. Public TLS and route
multiplexing belong to the reverse-proxy layer.



## Product and extension capabilities

Installed Gway products and extensions may publish remote authorization scopes and
read-only Survey contributors declaratively from their own `pyproject.toml`.
Gway discovers this metadata from managed installation records without importing
product code.

A product-owned scope is declared under `[tool.gway.scopes]`:

```toml
[tool.gway.scopes.example-read]
operations = ["example.status", "example.items"]
environment = []
```

The scope name becomes available to ordinary bearer-token and OAuth authorization.
Published scopes cannot replace Gway-owned core scopes, and conflicting definitions
from multiple installed projects are rejected rather than merged implicitly.

A product may also contribute a bounded section to the generic `survey` snapshot:

```toml
[[tool.gway.survey]]
section = "example"
command = ["example", "status"]
```

Survey commands are token arrays rather than shell strings. Gway executes each
contributor through the normal read-only observation boundary under the caller's
effective authority. A contributor whose operation is not authorized is omitted;
an unavailable contributor degrades independently in the same way as built-in
Survey sections. Section-name collisions are rejected. During the migration, legacy `[[tool.gway.watch]]` declarations remain accepted when `[[tool.gway.survey]]` is absent; projects must not declare both forms.

The built-in read scopes deliberately compose. Their union covers the complete
built-in Survey report: `logs-read` supplies recent errors, `source-read` supplies
deployment/release/queue observations, and `operator-read` supplies
node/services/Wire observations. Product-owned Survey sections require the
corresponding product-published operation grants.


## One-origin reverse proxy

The remote edge is intentionally one public HTTPS origin backed by two
independent loopback services:

```text
https://remote.arthexis.com
        |
      nginx
       / \
      /   \
 /mcp     OAuth/account routes
  |             |
127.0.0.1:8000  127.0.0.1:8001
MCP             remote-auth
```

The generic sampler lives in `sampler/web/remote`. Its defaults match the
maintained G-Way services, but the hostname and both upstreams are configurable.
For another deployment, provide a different `domain`, `mcp_host`,
`mcp_port`, `auth_host`, and `auth_port` without changing the templates.

The public routing contract is:

```text
/mcp
    -> MCP upstream

/
/.well-known/oauth-protected-resource/mcp
/.well-known/oauth-authorization-server
/oauth/authorize
/oauth/token
/oauth/revoke
/query
/login
/connect
/consent
/settings/connections
    -> remote-auth upstream
```

Only those application routes are exposed. There is no generic OAuth,
settings, well-known, or application catch-all proxy.

The HTTP listener reserves `/.well-known/acme-challenge/` for the local ACME
webroot and redirects every other request to the canonical HTTPS origin. It
never proxies MCP, OAuth, or account traffic in cleartext, including
during initial certificate bootstrap. The OAuth well-known endpoints are served
only through the HTTPS application server, so certificate renewal and OAuth
discovery do not compete for route ownership.

The MCP location is an exact `/mcp` route and keeps the upstream path intact.
It uses HTTP/1.1, disables proxy/request buffering and proxy cache, clears the
Connection header, and defaults read/send timeouts to 300 seconds. Those
timeouts can be overridden with `mcp_read_timeout` and `mcp_send_timeout`.

Both upstream services remain loopback-bound. Nginx is the only public network
edge and performs TLS termination and path routing only; it does not perform
OAuth or G-Way authorization.

The edge rejects requests with a missing Host header or a Host value other than
the configured domain before proxying. HTTPS permits TLS 1.2 and 1.3, suppresses
Nginx version disclosure, emits HSTS, `nosniff`, and a same-origin referrer
policy, and returns 404 for undeclared application paths. The interactive login
and OAuth token endpoints share a conservative per-client rate limit; MCP and
read-only query traffic are not subject to that limit.

## Remote exposure lifecycle

The remote sampler follows the same two-stage HTTP-01 deployment model as the
ordinary web exposure sampler:

```text
sampler/web/remote/expose.rx
    -> http.rx
    -> https.rx
```

The HTTP stage creates the shared ACME webroot, renders the temporary HTTP
topology, enables it, validates nginx, and reloads. The HTTPS stage obtains or
reuses the certificate with Certbot, renders the TLS topology, validates nginx,
and reloads.

Nginx mutations are protected by G-Way rollback journals. Render/link/remove
changes remain uncommitted until `nginx -t` and reload both succeed. A
validation or reload failure therefore restores the previous site state instead
of leaving an invalid configuration active.

Cleanup removes only the nginx site files. Certificates and the shared ACME
webroot are preserved.
