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
-L, --log-level LEVEL
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


## Operation documentation

Treat a callable's Python signature as the primary mechanical interface and keep
it easy to scan. Do not make signatures noisy merely to satisfy documentation
machinery.

Use docstrings for human-oriented meaning. Every public GWAY-owned operation
should have a concise first-line summary. Longer prose is optional.

When a parameter needs explanation beyond what its name, type annotation, and
default already communicate, document it in an `Args:` section:

```python
def install(source, upgrade=True, force=False):
    """Install a project into GWAY-managed storage.

    Args:
        source: Local path, Git URL, or known project identity.
        force: Replace a dirty managed installation and discard its local changes.
    """
```

Parameter entries are deliberately optional. In the example above,
`upgrade` needs no prose if its name and default are sufficiently clear.
Do not add filler descriptions merely to make every parameter appear in the
docstring.

GWAY documentation combines information from three sources:

```text
GWAY provenance   -> canonical path, operation/subject, source metadata
Python signature  -> parameter names, kinds, defaults, requiredness, annotations
Docstring prose   -> summary, long description, optional parameter explanations
```

The signature remains authoritative for mechanics. A docstring parameter entry
must explain meaning, not redefine its type, default, or requiredness. Type
annotations are useful when they clarify the Python interface but are not
required for documentation.

The preferred parameter section for GWAY-owned code is `Args:`, using
`name: description` entries. Documentation ingestion is intentionally
tolerant and may also understand common `Arguments:` and `Parameters:`
sections from imported Python code.

Undocumented parameters remain fully supported. Verbose help and interactive
guidance fall back to mechanical signature information whenever prose is
absent. Documentation quality checks must therefore never require prose for
every parameter.

Normal help is intentionally compact:

```text
gway help log config
```

Verbose help includes the full docstring and parameter details:

```text
gway -v help log config
```

Interactive mode uses the same metadata. `-i` keeps prompts terse, while
`-i -v` shows available parameter prose and mechanical facts before asking
for each missing required value.

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

Recipes are executable GWAY stages and use the same dispatcher from the CLI,
`Gateway(...)`, notebooks, chains, and nested recipes.

An explicit path always denotes a recipe stage:

```bash
gway ./example.rx
```

```python
gw("./example.rx")
gw(Path("./example.rx"))
```

A bare existing filename is also eligible as a recipe fallback when no already
registered GWAY operation resolves that command. Registered operations therefore
win ambiguous bare-name collisions, while explicit path syntax wins deliberately:

```text
deploy       # registered operation wins over ./deploy
./deploy     # explicit recipe reference
```

The legacy explicit CLI form remains supported:

```bash
gway -r ./example.rx
```

A recipe is a sequence of ordinary GWAY statements. Blank lines and comments
are ignored, and a physical line beginning with `--` continues the preceding
operation:

```text
# Charger setup
create charger
--serial ABC
--limit 32
inspect charger
```

Recipe arguments populate the same Gateway context before execution:

```bash
gway ./example.rx --site MTY --dry-run
```

Recipes do not introduce semantic scope. Every internal operation publishes
normally into the caller's shared results/context, so values published by
intermediate steps remain available after the recipe and to nested recipes.
Only raw positional flow is narrowed: without an explicit dash, recipe
newlines do not carry the previous raw result.

The recipe's raw output is simply the final operation's raw result. This makes
recipes ordinary pipeline stages:

```text
prepare.rx - summarize
produce - consume.rx
```

An incoming raw pipeline value feeds the first statement of a recipe; normal
newline semantics apply after that. A following dash receives the final
operation result. Existing tuple expansion and chain-local `[n]` / `[*]`
selectors therefore work unchanged on recipe output.

Nested relative recipe references resolve from the directory containing the
current recipe, not from the process working directory. Recursive recipe cycles
are rejected with a recipe call-stack error.

### Recipe companion scripts

Before any recipe statement is resolved, GWAY looks beside the resolved recipe
for a Python file with the same stem and a `.py` suffix:

```text
recipes/
    deploy.rx
    deploy.py
```

Executing `deploy.rx` first ingests `deploy.py` into the same Gateway. The
lookup is anchored to the recipe's own directory, never to the caller's current
working directory. Nested recipes independently discover companions beside
their own resolved paths.

Companions use ordinary Python path-ingestion semantics rather than a special
transparent namespace. Thus `deploy.py` exposes its public callable surface
under the normal `deploy` ingestion root, and the recipe can use operations
such as:

```text
deploy prepare charger
deploy execute
```

A missing companion is simply ignored. An existing companion that fails to
import aborts recipe execution before the first recipe statement runs.

Each resolved companion path is ingested at most once per Gateway instance.
This avoids replaying Python module import side effects when the same recipe is
executed repeatedly while keeping all companion operations available to later
recipes and commands through the shared runtime.

Top-level headings can still be selected as recipe sections by the loader:

```text
# Production
deploy charger

# Test
inspect charger
```

### Recipe controls and transactions

The complete user-facing recipe contract lives in `docs/RECIPES.md`. Keep
that document synchronized whenever recipe parsing, `check`, `repeat`,
semantic mapping lookup, companion loading, or rollback behavior changes.

Important current invariants:

- Recipe newlines and semicolons preserve named semantic context but do not
  transfer the previous raw result positionally.
- A standalone dash transfers the previous raw result.
- Mapping lookup is semantic: case, spaces, dashes, and underscores are
  equivalent. Ambiguous normalized keys are errors across every resolver
  surface, including sigils, nested paths, implicit argument completion, and
  `check`; do not catch ambiguity as an ordinary missing-key fallback.
- `check` is transparent on success and can validate booleans, whole-result
  equality, and semantic mapping fields.
- `check --unless BOOL` is evaluated before assertions. True skips the
  assertions; false evaluates them normally; non-booleans fail.
- `repeat` uses replayable execution records. Standalone repeat replays the
  previous operation, while repeat inside a pipeline replays the completed
  prefix of the current statement.
- `check --rollback NAME` and `repeat --rollback NAME` trigger rollback only
  on terminal control failure. Successful controls leave the journal open for
  explicit commit.
- Nested recipes share journals. Only the outer execution boundary performs
  automatic leak cleanup.
- A successful outer invocation may not silently retain an open journal. It
  automatically attempts rollback and raises `UncommittedJournalError`.
- When recovery also fails, preserve the original control/forward exception as
  primary and attach rollback recovery context.
- Rollback-aware mutation state is `PREPARED -> MUTATED -> APPLIED ->
  ROLLED_BACK`. Snapshot while PREPARED, mark MUTATED immediately before the
  underlying write begins, and mark APPLIED only after the post-state
  fingerprint is sealed. Never discard or blindly restore a MUTATED entry.
- The named rollback-journal mutation surface is currently `copy`, `move`,
  `link`, `remove`, and `render`. Any future operation that advertises a
  `rollback` argument must use this same lifecycle rather than performing a
  direct mutation first.

Do not copy recipe syntax from older branches or from aspirational documents
without checking the current parser and tests first.

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



## Clearing accumulated context

Each Gateway exposes a runtime-bound `clear` builtin. With no flags it clears
the current Gateway context:

```text
clear
```

Specific bare flags remove only those context keys:

```text
clear --site --charger
```

`clear` does not unregister operations and does not erase published result
history. It is a context-control operation, not a full Gateway reset.

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


### Chain-local positional sigils

Raw dash chains can reposition values from the immediately previous positional
result without turning those selectors into global sigil meanings.

When the previous raw result is a tuple, its elements form the positional
bundle for the next stage. Outside a raw chain, numeric and asterisk sigils keep
their ordinary semantic meaning.

Within a raw chain, an exact non-literal sigil containing a constant integer
selects that element from the original positional bundle:

```text
triple - combine [2] [0] [1]
```

uses the original third, first, then second tuple element. Indexing follows
normal Python/GWAY sequence indexing, including negative indices.

All numeric selectors in one stage are evaluated against the same immutable
snapshot. Repeating a selector duplicates that source value in the call while
marking its source slot consumed only once for purposes of the remaining pool:

```text
triple - combine [1] [1] [1]
```

An exact `[*]` sigil splices all values whose original source indices were
not referenced by any numeric selector in that stage:

```text
pair - combine manual [*]
```

If no `[*]` appears, all unselected positional values retain the normal
chain behavior and are inserted as a prefix before explicit positional
arguments. Numeric selection is computed for the whole stage before placement,
so a selector may appear before or after `[*]` without changing which source
values belong to the remaining pool.

Single-quoted forms such as `'[0]'` remain literal text and do not act as
chain selectors.


## Project discovery and configuration

Each new `Gateway` discovers the nearest `pyproject.toml` by searching from
the current directory upward. The current bootstrap does not use a separate
`gway.toml` manifest.

Standard Python packaging metadata is the primary project contract:

```toml
[project]
name = "arthexis"

[project.scripts]
arthexis = "arthexis:main"
```

Local `[project.scripts]` entries and conventional executable package
`__main__` surfaces are exposed through the same operation registry used by
manually ingested callables.

GWAY-specific semantic variables belong under:

```toml
[tool.gway.variables]
site = "MTY"
role = "Watchtower"
```

Those variables are appended as a resolver source and therefore participate in
ordinary semantic completion rather than a separate recipe configuration
system.

Managed installations are discovered from GWAY's durable installation registry.
Their project scripts and executable package-main surfaces are remembered
lazily and expanded through normal operation resolution. Durable installation
state is separate from disposable cache state.

Sous Chef discovery may also consume local or installed project metadata, but
project bootstrap should continue to prefer standard Python metadata and
inference over adding a second manifest language.

## Django ingestion

Django support is optional and lazily imported. Core GWAY has no mandatory
Django runtime dependency.

A conventional Django project can be mounted from its `manage.py` or from a
directory containing `manage.py`. A settings module can also be mounted
explicitly with `kind="django"`. Project mounting configures Django, indexes
the installed app registry, and remembers app/model branches lazily.

Apps are remembered as top-level branches. Models are remembered beneath their
Django app label, for example:

```text
energy.charger
sales.customer
```

When a model name is unique across the mounted registry, the model is also
remembered under its short semantic name such as `charger`. Duplicate model
names are not given an ambiguous short branch.

Django ORM sources are recognized automatically by `Gateway.ingest()`:

```python
gateway.ingest(Charger)
gateway.ingest(Charger.objects)
gateway.ingest(charger_instance)
```

Regardless of source type, ORM operations use the Django model name as their
semantic subject. Canonical paths retain app/model qualification where Django
metadata provides it. For example, the default manager's `filter()` method on
`energy.Charger` is registered canonically as:

```text
energy.charger.filter
```

with semantic identity:

```text
op = filter
sub = charger
```

so ordinary GWAY resolution can use:

```text
filter charger --status online
```

Ingesting a model class exposes its default manager methods plus explicit
class/static model methods. Ingesting a manager exposes that manager's public
callable surface on its model subject. Ingesting a concrete model instance also
exposes its bound public methods and stores that object in Gateway context under
the model subject so later semantic completion can reuse it.

Project-mounted models stay lazy: mounting a Django project does not eagerly
register every manager/model method. Resolving a model-scoped command such as
`filter charger` expands the remembered model branch and exposes its ORM
surface on demand.

Management commands are intentionally not part of the ORM layer. A Django
project mount records an optional project `name`; management-command exposure
is permitted only for named mounts and is implemented as a separate ingestion
layer.

### Django management commands

Only named Django project mounts expose management commands. An unnamed mount
indexes apps/models but does not create any management-command discovery branch.

For a named mount such as `arthexis`, GWAY reads Django's effective command
registry once and indexes only the command names as lazy resolution branches.
It does not eagerly register or execute the command implementations.

The first resolution of a command against that project, for example:

```text
migrate arthexis
```

expands only the matching indexed command and registers it canonically beneath
the project:

```text
arthexis.migrate
arthexis.collectstatic
```

with semantic identity such as:

```text
op = migrate
sub = arthexis
```

No bare top-level `migrate` or `collectstatic` aliases are created. This keeps
application-wide commands tied to the Django project subject.

Django command names containing underscores also receive only project-qualified
humanized aliases, so a command named `rebuild_search` can be called as:

```text
rebuild search arthexis
```

without creating a bare `rebuild search` operation.

Command execution delegates to Django's `call_command()`. Positional values and
GWAY keyword flags are forwarded to Django, and the command's return value is
published normally as the result of the project-scoped operation. Management
command discovery is idempotent per mounted project.

## Managed installation

GWAY exposes `install` and `uninstall` as core builtins. Their lifecycle
contract is binary and convergent: install means a project should be present at
the requested source/ref, while uninstall means it should be absent. There is
no separate upgrade operation. The install request carries `upgrade=True` by
default and therefore accepts `--no-upgrade` when a caller wants to suppress
replacement of an existing installation.

The current implementation supports local project directories and Git/GitHub
sources:

```text
gway install ./project
gway install ./project --system

gway install owner/project
gway install owner/project --ref feature-branch
gway install https://github.com/owner/project --ref main
gway install https://example.com/project.git --ref v1.2.3

gway uninstall project
```


GWAY itself follows this same contract. The repository declares:

```toml
[project]
name = "gway"

[project.scripts]
gway = "gway:cli_main"
```

and the bare source identity `gway` resolves to the Repository URL published
in GWAY's Python package metadata. Therefore self-install is ordinary source
resolution plus ordinary Git installation:

```text
gway install gway
gway install gway --ref gateway-rebuild
```

There is no `--self` path or separate self-update implementation. The running
process finishes with its already-loaded code; activation swaps the durable
launcher for future invocations.

Local filesystem intent wins before GitHub shorthand resolution. An existing
path is always treated as local, and explicit relative spellings such as
`./repo` or `../repo` are never reinterpreted as GitHub repositories.
A shorthand such as `owner/project` canonicalizes to
`https://github.com/owner/project.git`. Full GitHub HTTPS URLs with or
without `.git`, GitHub SSH shorthand, generic `ssh://`, `git://`,
`file://`, and HTTP(S) URLs ending in `.git` are also accepted Git sources.

Git support uses the system `git` executable and introduces no third-party
Python runtime dependency. Install metadata needed for `[project]` and
`[project.scripts]` has a narrow stdlib fallback on Python 3.10, so
self-install does not make `tomli` a core dependency. Full declarative
ingestion TOML parsing remains optional on Python 3.10 and is only invoked when
a manifest actually declares `[ingest]` or `[[ingest]]`. Each canonical repository has a mirror under the
general GWAY cache `git` namespace. Every install refreshes that mirror,
resolves the requested `--ref` (branch, tag, or commit) to an immutable commit
SHA, and materializes a detached content snapshot keyed by that SHA. Snapshot
trees contain no `.git` metadata. Cached snapshot fingerprints are verified
before reuse; a modified/corrupt snapshot is rebuilt.

The cache path is only a materialization detail. Authoritative installation
state records the canonical repository source, the requested ref, and the
resolved immutable commit separately from the durable managed project copy.
Deleting the Git cache must therefore never uninstall a project or erase which
revision is installed.

A moving branch naturally participates in normal convergence: rerunning the
same install command after the branch resolves to a different commit upgrades
the managed project by default. `--no-upgrade` keeps the already-installed
commit even though GWAY may refresh the repository mirror to discover the newer
remote state. A pinned commit becomes a stable no-op once installed.

A local source must be an existing directory containing `pyproject.toml` with a
non-empty, path-safe `[project].name`. GWAY computes a stable source
fingerprint from project paths, contents, symlink targets, and mode bits while
ignoring incidental VCS/tool-cache internals such as `.git` and
`__pycache__`.

Installation never writes into or mutates the source tree. GWAY stages a full
managed copy beneath the selected durable `projects/` directory, validates
that the staged project still has the expected identity and fingerprint, then
atomically activates the staged directory.

Projects declare command activation through standard `[project.scripts]`. Each
entry maps one command name to a `module:callable` target. GWAY creates an
executable launcher that prepends the durable managed project to `sys.path`
and invokes that target with the same Python interpreter running the installer.
User launchers default to `~/.local/bin`; system launchers default to
`/usr/local/bin`. `GWAY_BIN_DIR` and `GWAY_SYSTEM_BIN_DIR` override those
locations.

Launcher ownership is recorded under durable `launchers/` metadata. Project
directory replacement, launcher replacement, and SQLite state update form one
logical transaction: launcher activation is rolled back if state persistence
fails, and uninstall restores launchers if project/state removal fails. GWAY
will not overwrite or remove an unrelated executable that it does not own,
except that the currently executing same-name project launcher may be replaced
during its own installation.

Only after project and launcher activation succeed is the authoritative SQLite
installation record finalized. If any later state write fails, both the
launcher and project activation are rolled back.

Repeating an unchanged local install is a no-op and returns the existing
installation record. If the local source has changed, the default
`upgrade=True` path stages the new source beside the active installation,
renames the active tree to a temporary replacement backup, atomically activates
the staged tree, updates authoritative SQLite state, and only then removes the
backup. If the state update fails, GWAY removes the failed replacement and
restores the previous managed tree.

`--no-upgrade` leaves an existing managed installation untouched when the
source fingerprint has changed. A missing managed copy may still be repaired
under `--no-upgrade` when the source matches the recorded fingerprint; if the
source has also changed, GWAY refuses because that repair would implicitly
perform an upgrade.

Before any no-op, repair, or replacement, GWAY verifies that the live managed
tree still matches its recorded fingerprint. Drift is treated as evidence of
manual customization and blocks reconciliation by default rather than
overwriting those changes.

`--force` explicitly authorizes discarding that managed drift and rebuilding
from the requested source. GWAY emits a warning when force is used against a
dirty managed installation so callers know customizations are being discarded.

`--stash` is the preservation alternative. Before reconciliation, GWAY copies
the entire dirty managed tree into durable installation data under
`stashes/<project>/<timestamp-id>/tree` and writes adjacent `metadata.json`
containing source/ref provenance, scope, install path, recorded fingerprint, and
the actual dirty fingerprint. The stash is durable state, not cache, and is not
removed when cache data is cleared. After preservation succeeds, reconciliation
proceeds with the same clean replacement behavior as force.

Neither mutation override bypasses `--no-upgrade`. If the source itself has
changed and `--no-upgrade` is set, GWAY will not use that newer source as the
baseline for cleaning a dirty installation. When the source is unchanged,
`--force --no-upgrade` or `--stash --no-upgrade` may repair managed drift
because no source-version change is required.

If a caller points install at a different local source with the same project
name and identical content, GWAY updates source provenance without needlessly
replacing the managed tree.

Uninstall is idempotent. A managed project is first renamed to a tombstone,
then its authoritative state record is removed, then the tombstone is deleted.
If the state update fails, the live managed directory is restored. A missing
managed directory with a stale state record is reconciled by removing the stale
record. Registry paths outside the expected managed project location are never
deleted.

`--ref` applies to Git sources and may name a branch, tag, or commit. It is
rejected for ordinary local-directory sources. `--force` and `--stash` are
mutually exclusive mutation policies and remain orthogonal to Git source
selection: they handle drift in the managed installation, while `--ref`
selects desired repository state.

Durable installation state is separate from the disposable cache. User data
uses the platform data directory (`$XDG_DATA_HOME/gway` or
`~/.local/share/gway` on Linux), while system data uses a system location
(`/var/lib/gway` on Linux). `GWAY_DATA_DIR` and
`GWAY_SYSTEM_DATA_DIR` override those roots. Each scope reserves:

```text
projects/
stashes/
launchers/
state.sqlite
```

Launcher executables live in the scope's bin directory rather than inside the
managed project tree. This keeps generated activation state out of source
fingerprints and allows a stable command path to survive project replacement.

The SQLite registry is authoritative durable state and records project name,
source identity, requested ref, resolved revision, fingerprint, install path,
scope, and installation timestamp. Cache deletion must never remove these
records or durable project/stash data.

## Cache

GWAY has a general-purpose namespaced cache available as `Gateway.cache`. The
default root is outside project/source trees and follows the host platform:

```text
Linux/Unix:  $XDG_CACHE_HOME/gway or ~/.cache/gway
macOS:       ~/Library/Caches/gway
Windows:     %LOCALAPPDATA%/gway/cache
```

`GWAY_CACHE_DIR` overrides the default and is the preferred mechanism for
system/service deployments that need a shared location such as
`/var/cache/gway`. A caller may also construct `Gateway(cache=...)` with a
root path or an existing `Cache` instance.

Cache construction is lazy: creating a Gateway does not create cache
directories. A namespace is created only when a feature actually stores
something. Cache namespaces are intended for reusable artifacts and computed
state such as URL materializations, recipe compilation, parsed recipe data,
source hashes, and operation-discovery metadata. Arbitrary command results are
not transparently cached because side effects and external state require
command-specific invalidation semantics.

URL ingestion is the first cache consumer. HTTP(S) sources are materialized
under the `url` namespace using a stable URL key and content-addressed payload
directory. Metadata records the requested URL, final URL, content hash, and
materialized artifact path. A repeated URL uses the cached artifact unless
`refresh=True` is requested.

Remote code is never executed merely because it was downloaded. URL ingestion
requires `trust=True` before the cached artifact is delegated to ordinary
path ingestion:

```python
gateway.ingest("https://example.com/tools.py", trust=True)
```

Without trust, the artifact may be materialized into the cache, but execution
is rejected.

## Ingestion routing

Filesystem discovery is opt-in through explicit ingestion. Ordinary operation
resolution never probes the current directory or automatically exposes files.

`Gateway.ingest(source)` routes sources by explicit intent:

- Any `os.PathLike` value, including a relative `Path("README")`, is always
  treated as a filesystem source.
- A string containing path syntax such as `/`, `\\`, `~`, or a Windows
  drive prefix is treated as a filesystem source even if it does not exist.
- A bare string with no path syntax is treated as a filesystem source when an
  entry with that name exists in the current directory.
- Otherwise a bare string is treated as a Python import name.

For the ambiguous bare-name case, filesystem existence wins only because the
caller explicitly requested ingestion. Thus `gateway.ingest("json")` may
intentionally ingest a local entry named `json`, while executing
`gateway("json")` never discovers that file automatically.

Once something is classified as a filesystem source, it is always delegated to
`ingest_path()`. File extensions are not used to decide whether the source is
a path; they are only used later to select an available path ingestor. This
keeps extensionless files and future source types eligible for ingestion routing
without changing top-level path inference.
