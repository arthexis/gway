# GWAY logging

GWAY writes persistent structured execution events by default. The `log` operation changes metadata and synchronization targets for the current run; it does not enable or disable logging.

```text
gway log
gway log --tags watchtower,ubuntu22
gway log --to /tmp/gway-upload
gway log --tags watchtower,ubuntu22 --to /tmp/gway-upload
```

`--tags` and `--to` are additive. A bare `log` reports the current run ID, canonical local path, tags, and destinations.

## Filesystem destinations

A filesystem path or `file://` URL mirrors the run locally. When the destination is added, GWAY backfills events already written for the current run and then mirrors each new JSONL event into:

```text
<destination>/<run-id>/events.jsonl
```

The canonical local log remains authoritative.

## HTTP destinations

An `http://` or `https://` destination publishes NDJSON events to a GWAY Web log service. Set an ingest-scoped bearer token in `GWAY_LOG_TOKEN`, then point `--to` at either the service root or its `/api/logs` root:

```text
GWAY_LOG_TOKEN=gweb_v1_... gway log --to https://logs.example
```

GWAY posts to:

```text
<destination>/api/logs/<run-id>/events
```

If the destination already ends in `/api/logs`, GWAY appends only `<run-id>/events`. Existing events are backfilled when the destination is added, and later events are posted as they are written. Publication is best-effort and non-fatal: the canonical local log is still written first, and an unavailable remote endpoint does not make the command fail.

Bearer credentials are read from the environment and are never stored in the logging context or event payloads.

## Recipes

Put `log` near the start of a recipe to tag and mirror or publish the entire remaining execution:

```text
log --tags watchtower,ubuntu22 --to [log_destination]
upgrade gway --force
upgrade wire
```

Because recipe statements share one GWAY runtime, subsequent statement, operation, and recipe events use the configured tags and destination.

## GitHub Actions

A workflow can pass a runner-local staging directory into the recipe and upload it with `actions/upload-artifact`:

```yaml
- name: Execute recipe
  run: |
    gway recipe recipes/watchtower.rx \
      --log_destination "${RUNNER_TEMP}/gway-upload"

- name: Upload GWAY logs
  if: always()
  uses: actions/upload-artifact@v7
  with:
    name: gway-logs-${{ github.run_id }}-${{ github.run_attempt }}
    path: ${{ runner.temp }}/gway-upload/
```

This remains useful when no remote GWAY Web endpoint is configured.
