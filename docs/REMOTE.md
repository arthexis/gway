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
