# Source inspection

GWAY can inspect the implementation selected by its normal operation resolver. Source
inspection is operation-oriented: it does not expose a general filesystem search.

## Inspect an operation

```console
gway source env
gway source remote log
```

`source` returns the selected implementation's kind, path, line range, availability,
and source text when retrievable. Python operations and ingested recipes use the same
descriptor shape. Dynamic or generated implementations report that source is
unavailable instead of failing source discovery.

The target is resolved exactly as an ordinary GWAY command would be resolved. Extra
tokens that would be command arguments are rejected rather than silently inspected as
another target.

## Search one implementation

```console
gway source env --search default
gway source env --search default --context 1
```

`--search` searches only the already selected implementation. Match line numbers are
absolute source line numbers and context is bounded to that implementation.

## Search registered operation sources

```console
gway search source subprocess
gway search source service --kind recipe
gway search source token --topic security
```

`search source` searches registered, visible operation implementations rather than
walking repository files. `--kind` accepts implementation kinds such as `python` and
`recipe`. `--topic` filters explicit semantic topic metadata; a word merely appearing
in source text does not make that operation a member of the topic. Multiple topic
criteria are an intersection and their order does not change the corpus.

## Resolution diagnostics

```console
gway source status --all
```

`--all` reports the resolver-selected implementation and registrations shadowed by it,
in resolver precedence order. Normal execution is unchanged. The diagnostic uses
registrations retained by the operation resolver and does not reconstruct alternatives
by scanning files. `--all` and `--search` are intentionally separate modes.

## Authorization

Remote source inspection uses the dedicated `source-read` scope. That capability only
permits the `source` and `search source` operations; it does not grant visibility to
other operations.

Both gates must pass:

1. the caller is authorized to invoke source inspection; and
2. the target operation is already visible to that caller.

Corpus search applies the same target-visibility rule to every candidate, so hidden
operations do not leak through source matches, paths, kinds, or diagnostics.
