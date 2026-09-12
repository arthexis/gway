# GWAY Recipes

GWAY recipes are tracked in issue #883 and will use the `.rx` extension.

The first implementation step introduces a reusable statement executor without adding the recipe CLI yet. A statement uses the existing GWAY stage grammar, including `-` for explicit previous-result transfer.

`run_statement()` may receive a caller-owned context mapping. Results are published into that mapping while the statement runs, but the active context remains invocation-local and is restored afterward. This is the foundation for later recipe lines sharing named context without changing existing chain behavior.
