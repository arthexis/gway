# GWAY Recipes

GWAY recipes use the `.rx` extension and contain one GWAY statement per line.

Run a recipe with:

```text
gway recipe path/to/recipe.rx
```

Blank lines and lines whose first non-whitespace character is `#` are ignored. Arguments may be quoted so a single GWAY argument can contain spaces.

Each recipe runs in one persistent named context. Mapping values published by earlier statements may auto-populate later named options, while a newline never feeds the previous scalar result positionally.

Use `-` inside a statement when the previous stage result should be transferred positionally:

```text
demo scalar - demo echo
```

Compare that with separate statements:

```text
demo publish
demo consume
```

The second form shares named context only. Explicit arguments always take precedence over values found in recipe context.

Recipes fail fast. Errors include the recipe path and line number where practical.

`gway recipe -i` is reserved for the recipe REPL tracked as the next chunk of issue #883; this chunk intentionally does not implement the REPL yet.
