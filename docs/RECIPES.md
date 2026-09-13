# GWAY Recipes

GWAY recipes use the `.rx` extension and execute one GWAY statement per logical line through the same runtime evaluator used by the CLI.

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

Recipes are ordinary runtime stages, so they can participate in chains in either direction:

```text
producer - recipe deploy.rx - consumer
```

Incoming mapping values seed the child recipe's named context. Scalar incoming values are published only as the reserved `result`. Nested recipe contexts inherit readable parent values but child-local writes do not leak back automatically.

## Explicit recipe parameters

Named values can be supplied at invocation time:

```text
gway recipe deploy.rx --device gway-004 --fqdn register.arthexis.com
gway recipe deploy.rx --device=gway-004 --fqdn=register.arthexis.com
```

Dash-separated option names normalize to underscore context keys, so `--device-id` publishes `device_id`.

Explicit recipe parameters have the highest recipe-seeding precedence:

```text
explicit recipe parameters
-> incoming `-` result publication
-> inherited parent named context
-> environment/providers
-> defaults
-> `-i` prompt
```

`result` is reserved for GWAY result flow and cannot be supplied as an explicit recipe parameter. Recipes intentionally do not define a separate declaration/type/default language; syntactically valid non-reserved parameters are context seeds and may be consumed by any statement that resolves the matching name.

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

## Lifecycle operations and reload

The shared GWAY runtime can execute lifecycle operations from recipe statements as well as managed project commands:

```text
upgrade gway --force
reload
upgrade wire --force
```

`install`, `upgrade`, and `uninstall` use the same runtime boundary whether invoked from the CLI or from a recipe. Their returned values are published into recipe context using the normal result rules.

`reload` is the process-replacement boundary for self-upgrade workflows. GWAY persists a versioned checkpoint, replaces the process, restores transferable context/provenance, and continues from the saved recipe/chain continuation under the newly installed runtime. Nested recipes and pending parent chain stages are restored through the serialized continuation stack.

Reload state is intentionally portable data rather than pickled Python objects. If a checkpoint is incompatible, corrupted, or its recipe source changed, resume fails diagnostically instead of silently restarting from the beginning.

## Semantic success and failure

Managed commands that need to report execution status explicitly can return GWAY outcomes:

```python
from gway import failure, success

return success(value)
return failure(value, message="validation failed")
```

Successful outcomes unwrap before normal publication/transfer. Failed outcomes stop the current chain/recipe before the failed value can be published as a successful result. Ordinary mappings remain ordinary data, including `{"success": false}`; only the explicit GWAY outcome contract controls runtime failure.

## Explain and provenance

Runtime frames track statement/operation identity, recipe path/line, parent-child relationships, result producers, context publication, continuation pointers, and restored resume state. Explain traces therefore retain provenance across nested recipes, reload/resume, and semantic outcomes without using a separate execution model.

## CI and operational recipes

Operational recipes should live with the repository that owns the integration policy. A CI workflow should select a trusted checked-in `.rx` file and invoke it directly:

```text
sudo -n gway recipe recipes/ubuntu22-live.rx --fqdn register.arthexis.com
```

Keep host/environment assertions that are not GWAY operations—such as validating the runner OS or making a raw external HTTP request—in the workflow. Do not add shell escape, loops, branches, or background execution to `.rx` merely to move those checks into the recipe language.

## Errors

Recipes stop on the first failed statement. Parse and execution errors report the recipe path and source line when available. Resume/checkpoint failures are surfaced explicitly and do not restart work from the beginning.
