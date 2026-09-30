# Structured CLI output

GWAY separates console presentation from machine-readable sidecar output.

## `-j/--json`: change stdout presentation

Use `-j` when the caller wants stdout itself to be JSON:

```console
gway -j resolve '[site|MTY]'
```

Shell redirection remains the simplest way to capture that stdout:

```console
gway -j resolve '[site|MTY]' > result.json
```

## `-o/--output`: preserve the canonical result separately

Use `-o PATH` when human-readable stdout should remain available while another
system also needs the canonical final result:

```console
gway ci -o .gway/ci-result.json
```

The console output is unchanged. GWAY additionally serializes the final operation
or chain result as JSON and atomically replaces the requested file.

`-j` and `-o` are independent and may be combined. `--silent` suppresses console
presentation but does not suppress a requested sidecar.

For iterator/stream results, items continue to be emitted to stdout as they arrive;
the completed sequence is written to the sidecar only after iteration finishes.
An interrupted stream therefore does not leave a completed sidecar.

Serialization is strict. Values that cannot be represented by the current JSON
contract fail the invocation rather than being silently stringified. Output files
are written through a temporary sibling and replaced atomically so an interrupted or
failed write does not leave a valid-looking partial result.

The destination parent directory must already exist.

## Scope

Phase 1 supports JSON only. Future work may derive another format from the file
extension or add an explicit format option.

`-o/--output` is a CLI presentation/persistence concern, not a domain mutation, so
it does not change an operation's mutation classification and remains usable with
`--no-mutate`.

Programmatic Gateway/MCP calls intentionally do **not** accept `-o/--output` as a
leading global. MCP already returns structured values directly and its leading-global
allowlist rejects unsupported flags. If connector flags expand in the future, file
output must remain excluded unless a separate security design explicitly permits it.
