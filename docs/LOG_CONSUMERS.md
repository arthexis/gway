# Local log consumers

GWAY can wire managed applications on the same host to a remote GWAY Web log service without putting ingest bearer tokens in recipes.

```text
log --to https://logs.example.com --consumers wire,arthexis
```

`--consumers` accepts one or more comma-separated consumer names. The compatibility form `--consumer NAME` accepts exactly one name. Both forms may be used together and feed the same deduplicated consumer set.

When consumers are declared for an HTTP(S) destination, GWAY asks the locally registered `web` project for a `logs:ingest` bearer token. The token is reused while it remains active, is rotated when its server-side record is revoked or expired, and is never returned as part of the `log` command result.

The raw credential is retained only in GWAY's private data directory. Each consumer receives a mode-0600 systemd `EnvironmentFile` containing `GWAY_LOG_DESTINATION` and `GWAY_LOG_TOKEN`; generated service unit files reference that private file rather than embedding the token. A managed service whose project name or alias matches a declared consumer automatically receives the environment the next time its service unit is rendered/installed.

`GWAY_LOG_DESTINATION` also seeds the logging context for a fresh GWAY run. Therefore commands started inside a wired managed service publish through the configured destination without requiring another `log --to` operation.

Consumer wiring currently supports exactly one HTTP(S) destination per declaration and one active destination per consumer. Declaring an existing consumer against a different destination moves that consumer to the new binding.

Read credentials remain deliberately separate. External diagnostics clients should receive a dedicated `logs:read` token rather than the same-host ingest credential.
