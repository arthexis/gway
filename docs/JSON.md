# JSON mode

`--json` is a global GWAY output flag. It makes the final command or recipe result render as JSON and also publishes a boolean `json` value into the invocation's execution context.

Managed Python functions can opt in to JSON-aware behavior by declaring an ordinary boolean option:

```python
def status(*, json: bool = False):
    ...
```

With `gway --json project status`, GWAY supplies `json=True` when the caller did not provide that option explicitly. Without the global flag it supplies `json=False`. An explicit managed-command option still wins, so `gway --json project status --no-json` keeps the outer GWAY result in JSON while passing `json=False` to `status()`.

A function-level `--json` or `--no-json` is input to that call only. Passing it does not mutate shared context. Normal result publication still applies: if the function deliberately returns a mapping containing a `json` field, that field can become named context just like any other returned mapping field.

The same inherited context flows through chains, nested recipes, and reload/resume boundaries. Functions that do not declare a `json` option are unaffected.

Recipes can change the value explicitly for subsequent calls using the context operation whose job is to publish its parameters:

```text
store --json
project first
project second
```

and can turn it back off with:

```text
store --no-json
```

This recipe-level context changes what JSON-aware functions receive; it does not change the invocation's outer renderer. Use the global `--json` flag when the final GWAY output itself must be JSON.

Explicit recipe parameters can also override the inherited value using the unambiguous equals spelling, for example `--json=false`. Bare `--json` remains the global GWAY flag.
