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

The first synchronization transport accepts a filesystem path or `file://` URL. When the destination is added, GWAY backfills events already written for the current run and then mirrors each new JSONL event into:

```text
<destination>/<run-id>/events.jsonl
```

The canonical local log remains authoritative. Unsupported URI schemes are retained in the logging context so later transport plugins can implement them without changing recipe syntax.

## Recipes

Put `log` near the start of a recipe to tag and mirror the entire remaining execution:

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

This is deliberately a bridge rather than a GitHub-specific logging backend: GWAY owns the log and filesystem synchronization, while Actions owns artifact publication.
