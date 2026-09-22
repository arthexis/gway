# Logging

GWAY exposes logging as ordinary GWAY operations. The public surface is:

```text
gway log sources
gway log read [sources...]
gway log tail [sources...]
gway log search <pattern> [sources...]
```

These operations are used consistently by the CLI, recipes, Python callers, and
remote adapters such as MCP. There is no separate logging protocol.

## Logical sources

GWAY addresses logs by logical identity rather than by physical file or systemd
unit name.

Common identities are:

```text
gway
<project>
<project>/<service>
recipe/<identity>
```

For example:

```text
gway
arthexis
arthexis/web
arthexis/worker
recipe/deploy
```

`gway` identifies GWAY diagnostics. A project identity such as `arthexis`
is an aggregate over its installed service sources. A concrete service identity
such as `arthexis/web` resolves through persisted service-install state.
Direct recipe execution uses `recipe/<stem>`.

With no source argument, `read`, `tail`, and `search` operate on all
GWAY-managed sources known to the local installation. They never mean the
entire host journal.

## Reading logs

Read a bounded historical range:

```text
gway log read arthexis --since "10 minutes ago"
gway log read arthexis/web --limit 200
gway log read gway arthexis/worker --since 2026-09-22T12:00:00+00:00
```

Read the newest records:

```text
gway log tail
gway log tail arthexis
gway log tail arthexis/web --limit 50
```

`tail` is bounded and returns newest records first. Its default limit is 100.
Live follow/streaming is not part of the current logging API.

Search message content:

```text
gway log search timeout
gway log search "connection refused" arthexis
gway log search exception arthexis/web --since "30 minutes ago"
```

Search patterns are regular expressions. Journal-backed search is delegated to
the journal backend. Rotating-file search uses Python regular expressions.
Portable callers should use common regular-expression syntax rather than depend
on backend-specific extensions.

## Time bounds

The portable common subset for `--since` and `--until` is:

- timezone-aware ISO-8601 timestamps
- `now`
- `today`
- `N seconds ago`
- `N minutes ago`
- `N hours ago`
- `N days ago`

The journal backend may accept additional journal-specific forms, but recipes
and remote callers that need to work across platforms should use the common
subset.

## Storage backends

Logical logging identity is independent from storage.

On a host with a local journald-compatible socket, journald is GWAY's canonical
automatic durable backend. GWAY does not also create a private rotating log file
by default.

On a host without journald, including Windows, macOS, and Linux environments
without a journal socket, GWAY automatically uses its structured rotating-file
backend.

The selection is capability-based:

```text
journald available   -> journal
journald unavailable -> rotating JSONL file
```

Explicit output selection remains available through `--logfile` and the
Python logging configuration API.

### Rotating files

The portable durable path is:

```text
<GWAY data root>/logs/gway.log
```

Daily archives use:

```text
gway.log.YYYY-MM-DD
```

GWAY keeps up to 30 days total, including the active file.

Durable file entries are JSON Lines containing the normalized source identity,
timestamp, level, logger, message, PID, and unit fields. Pre-structured legacy
text rows are ignored by structured reads rather than guessed back into typed
records.

## Runtime backend versus log backend

A service runtime backend and its log storage backend are separate concerns.

Typical combinations are:

```text
systemd runtime -> journald storage
process runtime -> rotating-file storage on non-journald hosts
```

Process-backed GWAY services propagate their logical
`<project>/<service>` identity into the child GWAY process. GWAY does not
currently capture arbitrary subprocess stdout/stderr as a structured logging
stream.

## Query model

Internally, discovered identities are represented as descriptive `LogSource`
values. Backends normalize records into immutable `LogRecord` values. Public
operations serialize those records into ordinary GWAY result data.

Where possible, multiple journal sources are queried together so journald
performs native ordering. If more than one read backend is needed, GWAY merges
the normalized results by timestamp and applies the global limit afterward.

Raw journal metadata is intentionally not part of the default public result.

## MCP and other remote callers

Logging requires no MCP-specific API. The canonical GWAY operation identities
for read-only remote logging are:

```text
log sources
log read
log tail
log search
```

An MCP authorization scope should grant those ordinary operation identities.
The generic MCP `gway(command)` bridge then invokes the same commands used
locally, for example:

```text
gway(command="log tail arthexis --limit 20")
```

Authorization remains the responsibility of the generic GWAY dispatch layer.
Logging does not define separate `logs:read` permissions, HTTP endpoints,
publisher/provider bindings, or a logging-specific database.

## Deferred extensions

The current foundation intentionally does not add:

- live `log follow`
- arbitrary structured journal-field queries
- `log around` or `log stats`
- offset/page-based log slicing
- arbitrary subprocess stdout/stderr capture
- remote log forwarding

Those can be added independently when a concrete use case requires them.
