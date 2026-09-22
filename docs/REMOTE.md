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

A systemd deployment can be installed with the ordinary service controller:

```text
gway service install --backend systemd \
  --environment GWAY_CACHE_DIR=/var/lib/gway/cache \
  remote serve

gway service start remote serve
gway service status remote serve
gway service restart remote serve
gway service stop remote serve
```

The cache override is important for a system installation because OAuth links,
grants, access tokens, refresh tokens, and named G-Way security policy live in:

```text
$GWAY_CACHE_DIR/security/state.sqlite
```

That database is outside replaceable application code and outside the generated
systemd unit. Reinstalling the service or upgrading G-Way therefore does not
reissue or discard OAuth state.

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
/login
/connect
/consent
/settings/connections
    -> remote-auth upstream
```

Only those application routes are exposed. There is no generic OAuth,
settings, well-known, or application catch-all proxy.

The HTTP listener reserves `/.well-known/acme-challenge/` for the local ACME
webroot. After a certificate exists, all other HTTP traffic redirects to HTTPS.
The OAuth well-known endpoints are served only through the HTTPS application
server, so certificate renewal and OAuth discovery do not compete for route
ownership.

The MCP location is an exact `/mcp` route and keeps the upstream path intact.
It uses HTTP/1.1, disables proxy/request buffering and proxy cache, clears the
Connection header, and defaults read/send timeouts to 300 seconds. Those
timeouts can be overridden with `mcp_read_timeout` and `mcp_send_timeout`.

Both upstream services remain loopback-bound. Nginx is the only public network
edge and performs TLS termination and path routing only; it does not perform
OAuth or G-Way authorization.

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
