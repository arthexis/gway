# Recipe design research

Gway recipes are intentionally opinionated.

A recipe is not meant to expose every implementation decision as a parameter.
Its value comes from recording a sequence of choices that has already been
shown to work. The author should choose sensible tools, ordering, defaults, and
boundaries so that the caller supplies only the few pieces of information that
actually vary at the level of the task.

## Think like a cooking recipe

A useful cooking recipe does not normally say:

- choose any oven temperature;
- choose any cooking time;
- choose any ratio of flour to water;
- choose whether to bake, boil, or fry at each step.

Those are the decisions the recipe is supposed to encode. Giving the cook a
switch for every decision makes the instructions less useful and creates more
ways to produce a bad result.

A good variable is something like **servings**. Servings is a high-level fact
about the whole recipe. It can legitimately influence ingredient quantities
throughout the remaining steps.

The same rule applies to Gway recipes. A deployment recipe may reasonably carry
ambient facts such as:

```text
host
domain
site
email
```

when those facts describe the deployment as a whole. It should not put every
local operation argument into ambient context merely because an operation
accepts that argument.

Another cooking analogy is salt. If one step says "add 5 g of salt", that
quantity belongs to that step. It should not become a global `salt` variable
unless the whole recipe genuinely needs to reason about total salt.

## Context is intentional ambient configuration

Recipe context is a commitment by the author:

> This value has one semantic meaning that downstream steps are expected to
> share until it is overridden or cleared.

Therefore use the shortest semantic name that is unambiguous in the recipe's
conceptual scope.

Good:

```text
host
port
domain
endpoint
```

when there is one primary host, port, domain, or endpoint.

Use a prefix when it changes the meaning rather than merely as defensive
namespacing:

```text
host
database_host
callback_host

path
certificate_path
log_path
```

Here the prefixed names identify genuinely different concepts.

Do not mechanically prefix every parameter with the recipe name. Inside an
`mcp/server` recipe, `host`, `port`, `path`, and `endpoint` already have
a clear local meaning. Writing `mcp_host`, `mcp_port`, and so on repeats the
namespace without adding semantic information.

If two downstream operations unexpectedly compete for a generic context name,
first ask whether that value should have been ambient at all. Often the correct
fix is to keep one or both values local to the operation that consumes them,
not to invent longer names for everything.

## Prefer decisions over options

Treat a large parameter surface as a design smell.

Before adding a recipe parameter, ask:

1. Is this a high-level fact the caller genuinely knows better than the recipe?
2. Does the value intentionally affect more than one downstream step?
3. Is there more than one proven configuration that this same recipe should
   support?
4. Would fixing the value encode a useful operational decision instead?

If the answer is mostly no, keep the decision inside the recipe.

When substantially different choices are both valid, separate recipes are
often clearer than one recipe with many conditionals. A cooking book has a
bread recipe and a cake recipe; it usually does not have one giant
`bake --bread-or-cake ...` recipe.

## Keep conditionals rare and high-level

Recipes should normally be linear. Real-world procedures that have been tested
and operationalized tend to have a known sequence.

A conditional is appropriate when it represents a high-level property of the
task. Servings is again a useful analogy: changing servings scales quantities
through the recipe. A deployment mode may similarly select a coherent branch.

Conditionals that independently toggle many individual steps usually indicate
that the recipe is trying to represent several different procedures at once.

## Recipe parameters are intentionally ambient

Gway recipe arguments become shared semantic context before the recipe runs.
That is useful, but it means recipe authors should treat every recipe parameter
as an ambient decision that downstream steps may consume.

For example:

```text
gway ./deploy.rx --host 127.0.0.1 --domain remote.example.com
```

is appropriate when `host` and `domain` describe the deployment as a whole.

The same rule applies when one recipe invokes another:

```text
recipe mcp/server
--host 127.0.0.1
--port 8000
--path /mcp
--endpoint https://remote.example.com/mcp
```

Those names enter shared semantic context. They are still good names because the
recipe is intentionally saying that these are the primary host, port, path, and
endpoint for the procedure being composed.

This is why generic context names must be chosen deliberately. If a parent
recipe is about to orchestrate several unrelated paths, defining a generic
`path` in ambient context is probably a mistake. Keep step-specific values as
ordinary operation arguments, or give truly distinct ambient concepts semantic
names such as `certificate_path` and `log_path`.

Do not solve this by mechanically prefixing every recipe parameter. Prefixes
should distinguish concepts, not compensate for overusing ambient context.

One practical warning is `path`: generic semantic names can collide with
other values that legitimately occupy the same semantic position. In that
situation, choose the real concept instead of adding a defensive namespace
prefix. For an HTTP server, `route` is semantically better than `mcp_path`:
it describes what the value means.


A useful rule is:

> Put a value in recipe parameters/context only when you intend downstream
> operations to share that meaning. Otherwise pass it directly to the operation
> that needs it.

## Semantic configuration and environment interoperability

Environment variables are not semantic context. They are literal execution
state. Gway configuration should name meaning first and let bindings describe
physical representations.

For example, a project-wide cache location belongs in semantic configuration:

```toml
[tool.gway.variables]
cache_dir = "/var/lib/gway/cache"
```

A provider or deployment may instead register physical compatibility bindings
for the same semantic value. The recipe still consumes `[cache_dir]`; it does
not need to know which representation supplied it.

`set env` remains available when a downstream external program requires a
literal environment variable:

```text
set env LEGACY_VENDOR_MODE production
run legacy-tool
```

Everything that runs afterward in that recipe sees the override. Child recipes
inherit it, nested overrides restore correctly, and the original process
environment is restored when the outer recipe finishes.

The dashed spelling `set-env` is equivalent. Use `clear env NAME` (or
`clear-env NAME`) to hide one literal variable for the remainder of the
current recipe scope.

A useful rule is:

> Semantic meaning belongs in context/configuration and bindings. Literal
> environment identity belongs in `env` operations only when that identity is
> part of an interoperability contract.

Do not use `set env`, `env NAME`, or service `--environment` as an
alternate configuration system for Gway itself.

## Design test

A good recipe should feel like instructions from an experienced operator or
cook:

> Give me the few facts I cannot know, then follow the proven procedure.

If using a recipe requires understanding and selecting every low-level choice,
the recipe is probably not encoding enough knowledge.
