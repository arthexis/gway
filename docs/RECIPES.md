# GWAY Recipes

GWAY recipes use the `.rx` extension and execute one GWAY statement per logical line.

Run a recipe with:

```text
gway recipe path/to/file.rx
```

Blank lines and full-line `#` comments are ignored. Each statement is tokenized as GWAY input rather than executed by a shell.

## Context and chaining

Recipe statements share named context. Mapping results publish their keys into the accumulated recipe context, so later commands may resolve omitted named parameters from earlier results. The complete latest result is also available through the reserved `result` operation.

Newlines carry named scope/context; they do not transfer a scalar result positionally:

```text
producer
consumer
```

Here `consumer` can resolve matching named values from accumulated context, but it does not receive the previous scalar result as a positional argument.

Use `-` when the previous result should feed the next stage positionally:

```text
producer - consumer
```

In short:

```text
newline  -> shared named scope/context
-        -> immediate previous-result transfer
```

Explicit command arguments take precedence over values resolved from context.

## `store` and `result`

Use `store` to publish named values explicitly into recipe context:

```text
store --customer cust-9 --charger chg-9
```

Use `result` to reproduce the latest captured result, or a Sigil expression to extract a named value:

```text
result
result [customer]
```

These are ordinary runtime operations and follow the same result-publication rules as managed commands.

## Interactive execution

`-i` / `--interactive` keeps its normal GWAY meaning for recipes: prompt for required values that remain missing after explicit arguments and accumulated recipe context are considered.

Both placements work:

```text
gway -i recipe deploy.rx
gway recipe -i deploy.rx
```

## Lifecycle operations

The shared GWAY runtime can execute lifecycle operations from recipe statements as well as managed project commands:

```text
install arthexis
arthexis status
uninstall arthexis
```

`install`, `upgrade`, and `uninstall` use the same runtime boundary whether invoked from the CLI or from a recipe. Their returned values are published into recipe context using the normal result rules.

Self-upgrading GWAY changes the installed files but does not reload code already imported by the running process. Resuming execution under newly installed GWAY code requires the planned reload/checkpoint support and is not currently implied by `upgrade gway`.

## Errors

Recipes stop on the first failed statement. Parse and execution errors report the recipe path and source line when available.

Recipe composition as a chain stage and reload/checkpoint continuation are intentionally deferred to later recipe-runtime work.
