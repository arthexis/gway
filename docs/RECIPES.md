# GWAY Recipes

GWAY recipes use the `.rx` extension and execute one GWAY statement per logical line.

Run a recipe with:

```text
gway recipe path/to/file.rx
```

Blank lines and full-line `#` comments are ignored. Each statement is tokenized as GWAY input rather than executed by a shell.

Recipe statements share named context. Mapping results publish their keys into the accumulated recipe context, so later commands may resolve omitted named parameters from earlier results. Newlines do not transfer scalar results positionally.

Use `-` inside a statement when the previous result should feed the next stage positionally:

```text
producer - consumer
```

This differs from:

```text
producer
consumer
```

where `consumer` can see accumulated named context but does not receive the previous scalar result as a positional argument.

`-i` / `--interactive` keeps its normal GWAY meaning for recipes: prompt for required values that remain missing after explicit arguments and accumulated recipe context are considered.

Both placements work:

```text
gway -i recipe deploy.rx
gway recipe -i deploy.rx
```

Recipes stop on the first failed statement and report the recipe path and line number.
