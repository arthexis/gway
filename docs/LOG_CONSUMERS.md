# Local log consumers

GWAY can wire managed applications on the same host to a remote GWAY Web log service without putting ingest bearer tokens in recipes.

```text
log --to https://logs.example.com --consumers wire,arthexis
```

`--consumers` accepts one or more comma-separated consumer names. The compatibility form `--consumer NAME` accepts exactly one name. Both forms may be used together and feed the same deduplicated consumer set.

When consumers are declared for an HTTP(S) destination, GWAY asks the locally registered `web` project for a `logs:ingest` bearer token. The token is reused while it remains active, is rotated when its server-side record is revoked or expired, and is never returned as part of the `log` command result.

The raw credential is retained only in GWAY's private data directory and the logger's process-local publisher state. It is **not** exported into the shared environment of the GWAY process, so unrelated managed commands and subprocesses do not inherit it. GWAY exports only a non-secret pointer to the private consumer-state file when reload/exec continuity is required.

Each explicitly declared service consumer receives a mode-0600 systemd `EnvironmentFile` containing `GWAY_LOG_DESTINATION` and `GWAY_LOG_TOKEN`; generated service unit files reference that private file rather than embedding the token. A managed service whose project name or alias matches a declared consumer automatically receives the environment the next time its service unit is rendered/installed.

Canonical project names and registered aliases represent the same consumer identity. If a consumer is later declared through another alias or moved to another destination, GWAY collapses that binding to the canonical identity and removes the obsolete local environment file.

`GWAY_LOG_DESTINATION` seeds the logging context for a fresh GWAY run started inside a wired managed service. Therefore commands started by that service publish through the configured destination without requiring another `log --to` operation.

Consumer wiring currently supports exactly one HTTP(S) destination per declaration and one active destination per consumer. Declaring an existing consumer against a different destination moves that consumer to the new binding.

Read credentials remain deliberately separate. External diagnostics clients should receive a dedicated `logs:read` token rather than the same-host ingest credential.
