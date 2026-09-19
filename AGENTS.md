# GWAY Agent Guide

This branch is the minimal GWAY Gateway rebuild. This document describes how
GWAY works **today**. Treat it as an operating guide, not a roadmap: do not
infer planned syntax or future features from older branches, issues, or
historical implementations.

## Core principle

GWAY is a small Python command-dispatch and composition core. It exposes Python
callables as operations, binds command input to their signatures, completes
missing semantic values from runtime context, invokes the callable, and
publishes its result for later operations.

A typical operation is named with a verb and semantic subject:

```python
def get_charger():
    ...

def inspect_charger(charger):
    ...
```

The subject of both operations is `charger`. A result published by
`get_charger` can therefore satisfy the `charger` argument of a later
`inspect_charger` operation without the caller spelling the value again. More
generally, any still-unbound concrete parameter can be completed from a named
runtime value with the same parameter name.

Keep Python responsible for Python control flow and domain logic. Recipes are
for declaring and composing operations.

## Running GWAY

Install the package in editable mode:

```bash
python -m pip install -e .
```

## Local agent validation

Agents working on GWAY should install the active branch into their local
execution environment whenever that environment permits it. Treat the local
editable install as the preferred way to answer questions about current GWAY
behavior and to prove requested changes before relying only on code inspection
or remote CI.

A good working layout is a stable checkout directory dedicated to the active
branch, for example:

```text
/mnt/data/gway-gateway-rebuild
```

or, in a normal developer environment:

```text
~/src/gway
```

Install from the repository root:

```bash
cd /mnt/data/gway-gateway-rebuild
python -m pip install -e .
```

Then verify the actual runtime directly. Prefer concrete executions such as:

```bash
python -c "import gway; print(gway.__file__)"
gway --help
gway env PATH
python -c "from gway import gw; print(gw('env PATH'))"
```

When a user asks whether a feature works, how a command behaves, or whether a
change solved a problem, agents should run the relevant GWAY command or Python
call locally whenever possible and report the observed result. Direct runs are
especially valuable for dispatch, ingestion, sigils, recipes, chaining,
argument binding, publication, and notebook-style embedding.

Keep the editable install pointed at the same checkout being modified. After
changing source files in an editable install, a reinstall is normally not
needed; rerun the relevant command/tests directly. Reinstall only when package
metadata, build configuration, interpreter environment, or the checkout path
changes.

Some sandboxed or CI-like agent environments cannot reach PyPI. In those
environments, the normal editable install may fail while pip tries to create an
isolated build environment and download build requirements. If setuptools and
wheel are already available locally, use:

```bash
python -m pip install --no-build-isolation -e .
```

This is the preferred no-network workaround. Do not mistake a build-isolation
dependency download failure for a GWAY runtime failure.

If the repository is not already present locally, materialize or download the
active branch into a writable checkout directory first, then install from that
directory. Prefer the exact branch under development rather than an older PyPI
release, because validation should reflect the code the user is asking about.

Remote CI remains important for supported-version coverage, but it complements
rather than replaces direct local execution. The ideal validation sequence is:

```text
edit
  -> direct local GWAY run
  -> focused local tests
  -> full local tests when practical
  -> remote CI
```


The CLI entry point is `gway`. With no operation or expression it prints
help.

Current global options are:

```text
-d, --debug
-i, --interactive
-j, --json
-r, --recipe PATH
-t, --timed
-v, --verbose
-z, --silent
-e, --expression EXPR
```

Examples:

```bash
gway get charger
gway set limit --limit 32
gway -e "[site]"
gway -r ./deploy.rx --site MTY
```

Operation resolution uses the longest leading token sequence that resolves to a
callable. GWAY tries space-separated, underscore-separated, and dotted forms,
so an exposed `get_charger` operation can be addressed naturally as
`get charger` when the runtime exposes that callable.

## Arguments and Python signatures

Explicit command arguments are bound against the Python callable signature.

Positional input:

```bash
gway echo hello
```

Keyword input:

```bash
gway set limit --limit 32
```

Boolean parameters can be supplied as bare flags:

```bash
gway configure charger --enabled
```

The standalone `--` ends option parsing. Everything after it is positional
input even if it begins with `--`.

Binding performs signature-aware conversion for explicit command input.
Currently `int`, `float`, and `bool` annotations receive primitive
conversion. Direct Python calls to wrapped functions are not silently retyped;
CLI/recipe conversion belongs to the binding boundary.

With `--interactive`, missing required arguments are prompted for before
semantic completion.

## Quoting

GWAY preserves quote provenance in recipe tokens.

Single quotes mean opaque literal text:

```text
echo '[site]'
echo '32'
echo '--special'
```

Those values are not interpreted as sigils or coerced through type annotations.

Double quotes group text but retain normal GWAY interpretation:

```text
echo "[site]"
set limit --limit "32"
```

A double-quoted sigil can resolve, and double-quoted numeric text can still be
converted according to the Python signature.

A standalone unquoted `-` is a raw positional pipeline separator. A standalone
unquoted `;` is a statement boundary with the same named-context continuity as
a recipe newline. Quoted separators are ordinary values.

## Recipes

Recipes are loaded from an explicit filesystem path:

```bash
gway -r ./example.rx
```

A recipe is a sequence of operations. Blank lines and comments are ignored.

Example:

```text
# Charger setup
create charger --serial ABC
inspect charger
```

A physical line beginning with `--` continues the preceding operation:

```text
configure charger
--limit 32
--enabled
```

Top-level headings can be used as recipe sections by the recipe loader:

```text
# Production
deploy charger

# Test
inspect charger
```

Recipe CLI arguments such as:

```bash
gway -r ./example.rx --site MTY --dry-run
```

are parsed into the Gateway context before the recipe executes.

Do not rely on implicit bundled recipe lookup. The current loader expects an
explicit path.

## Gateway wrapping and execution

`Gateway.wrap(name, callable)` is the normalization entry point for Python
operations. The old `wrap_callable` API is removed.

The current execution path is deliberately separated:

```text
binding
  -> semantic completion
  -> invocation
  -> publication
```

The implementation lives in:

```text
gway/binding.py
gway/normalization.py
gway/invocation.py
gway/publication.py
```

`Gateway.wrap()` is the façade tying those pieces together.

Semantic completion can fill any still-unbound concrete parameter from runtime
state using the parameter name, regardless of whether Python would ordinarily
receive that parameter positionally or by keyword. Explicit/native arguments
and dash-pipeline positional values take precedence; defaults and Sigil defaults
are used only after named semantic lookup. Variadic collectors (`*args`,
`**kwargs`) are not semantic lookup slots.

Invocation supports synchronous and awaitable callables. Timing policy is
handled at the invocation boundary.

## Results and context

Gateway resolution currently searches sources in this order:

```text
results
context
environment
```

That precedence matters. A published result with a matching name shadows an
ordinary context value, which shadows an environment variable.

Published results are retained under their semantic subject:

```python
get_charger() -> "CHG001"
# results["charger"] == "CHG001"
```

Mapping results are also preserved as the value of their subject rather than
being flattened into the results mapping.

For current composition behavior, mapping results are additionally merged into
Gateway context:

```python
inspect_charger() -> {"serial": "ABC", "online": True}

# results["charger"] is the mapping
# context["serial"] == "ABC"
# context["online"] is True
```

Publishing another value under the same subject replaces the previous value.

## Sigils

A Sigil is a semantic reference, not a lexical token and not a storage
location.

The design lineage comes from contextual token-resolution systems used in
Project and Portfolio Management software, but GWAY deliberately calls these
values *sigils*: a token is a lexical unit, whereas a sigil has contextual
meaning.

The central rule is:

> A sigil identifies meaning. It does not specify where that meaning is stored.

For example:

```text
[charger]
[charger serial]
[response payload chargers 1 serial]
[chargers [index]]
```

The caller does not manually choose a result map, context dictionary, or
environment source. The active resolver determines the value from its ordered
sources.

### Sigil constructor

The explicit constructor implies the outer brackets:

```python
Sigil("charger")
```

is equivalent to:

```python
Sigil("[charger]")
```

Already-bracketed input is accepted without double-wrapping.

Brackets inside constructor input mean nested sigils:

```python
Sigil("chargers [index]")
```

represents:

```text
[chargers [index]]
```

Sigil instances are context-free. They do not capture or hide a Gateway,
mapping, environment, or other resolver.

### Resolution

Normal string expressions require explicit brackets:

```python
gateway.resolve("[site]")
gateway.resolve("[charger serial]")
```

Nested sigils resolve selectors dynamically:

```python
gateway.context["field"] = "serial"
gateway.context["charger"] = {"serial": "ABC"}

gateway.resolve("[charger [field]]")
# "ABC"
```

Paths can traverse mappings, sequences, and object attributes.

Quoted keys inside a sigil are still lookups, not string literals:

```python
gateway.context["status code"] = 200
gateway.resolve('["status code"]')
# 200
```

An unresolved sigil raises `KeyError` unless the resolver call explicitly
supplies a default.

### The modulo operator

`%` is an explicit resolution operator. It is **not** an eagerness marker.

A context-free Sigil can be resolved against a context:

```python
Sigil("site") % gateway
Sigil("site") % {"site": "MTY"}
```

Gateway/Resolver instances can resolve expressions from the other direction:

```python
gateway % Sigil("site")
gateway % "[site]"
```

Where Python's reverse-operator protocol permits it, `context % sigil` is
also handled by `Sigil.__rmod__`.

The old embedded eager form:

```text
%[site]
```

is not part of the current sigil syntax.

### Sigil implementation layout

Sigil behavior is organized as a package:

```text
gway/sigil/
    __init__.py
    value.py       # context-free Sigil value
    resolver.py    # source precedence and Resolver API
    resolution.py  # expression resolution
    paths.py       # mapping/sequence/attribute traversal
    spool.py       # ordered Sigil alternatives
```

Import sigil primitives from `gway.sigil` (or from the public `gway` package).
There is no parallel `gway.sigils` module.

## Composition model

The useful mental model for current GWAY execution is:

```text
command text
  -> lexical tokens
  -> operation resolution
  -> explicit argument binding
  -> semantic argument completion
  -> invocation
  -> publication
  -> later operations resolve from the updated runtime
```

This is why operation names, Python parameter names, semantic subjects, results,
context, and sigils work together. Prefer composing operations through those
contracts rather than manually passing values that GWAY can resolve
semantically.

## Module and package naming

Use single-word module and package names wherever practical. Do not introduce
underscore-separated implementation module names such as `sigil_paths.py` or
`argument_binding.py`; group related behavior into a package and use focused
single-word modules inside it.

`__init__.py` and `__main__.py` are standard Python dunder modules and are the
intentional exceptions to this naming rule.

## Repository scope

Keep this repository focused on GWAY core mechanics. Do not add bundled domain
projects, framework-specific integrations, deployment tooling, or third-party
runtime dependencies unless the architecture explicitly requires them.

The current baseline must remain importable and runnable with no third-party
runtime dependencies.

## Testing

Prefer tests of current supported behavior and architecture contracts. Do not
add tombstone tests whose only purpose is to assert that a removed API, module,
alias, compatibility shim, legacy helper, or historical implementation detail
continues to be absent. Once obsolete code is deleted, its absence is not a
feature that needs permanent test coverage.

This does not prohibit negative tests for current behavior. Tests should still
verify meaningful present-day constraints, such as rejecting invalid input,
refusing unsupported paths, preserving security boundaries, or ensuring that
plain context values are not executable operations. The distinction is that a
negative test should protect a current contract, not memorialize deleted code.

When removing an API or compatibility layer, remove tests dedicated only to
that retired surface as part of the same cleanup. Test the replacement/current
contract positively instead of adding assertions such as `not hasattr(...)`,
`find_spec(...) is None`, or checks for old names solely because they used to
exist.

Install pytest and run the complete suite:

```bash
python -m pip install -e .
python -m pip install pytest
python -m pytest -q
```

CI currently exercises the suite on Python 3.10 and Python 3.13.

When refactoring, preserve behavioral contracts first. Move/reorganize tests
only after the implementation remains green, unless the change intentionally
modifies a public contract.


### Statement context versus dash pipelines

Recipe newlines and standalone semicolons begin new statements without carrying
the previous raw result as an unnamed positional value. Named semantic state
remains continuous across those boundaries: published results, context values,
and environment-backed resolution are still available by name.

A standalone dash keeps the same named semantic state and additionally offers
the immediately previous raw result to the next stage as positional input. Dash
transport is positional: it does not require producer/consumer subject names to
match. A scalar raw result contributes one leading positional value. A tuple raw
result is a positional bundle and expands into multiple leading positional
values; lists and other iterables remain single positional values. Explicit
positional arguments on the chained operation follow that pipeline prefix. Any
remaining concrete parameters may then be completed from named semantic context
by parameter name.
