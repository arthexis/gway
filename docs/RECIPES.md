# GWAY Recipes

GWAY recipes are small, reviewable programs made from ordinary GWAY operations and control stages. They use the same dispatcher, semantic context, publication rules, and rollback machinery as the CLI and Python Gateway API.

Recipes are intentionally not a replacement for Python. Put algorithms, protocol details, complex branching, and reusable implementation logic in Python operations. Use .rx files to compose those operations into readable operational intent.

## Running a recipe

An explicit recipe path can be executed directly:

~~~text
gway ./recipes/deploy.rx
~~~

The legacy explicit CLI form is also supported:

~~~text
gway -r ./recipes/deploy.rx
~~~

From Python:

~~~python
from pathlib import Path
from gway import gw

gw("./recipes/deploy.rx")
gw(Path("./recipes/deploy.rx"))
~~~

A bare existing filename is eligible as a recipe only when no registered operation resolves the same command. Use an explicit path such as ./deploy when recipe intent must win an ambiguous name.

## Statements, context, and raw pipelines

A newline begins a new statement. Named semantic context remains available, but the previous raw result is not automatically passed positionally.

A semicolon has the same statement-boundary behavior inside one logical command.

Use a standalone dash to transfer the previous raw result into the next stage:

~~~text
produce - consume
~~~

The useful distinction is:

~~~text
newline / ;   shared named semantic context
-             raw previous-result pipeline
~~~

A recipe can itself participate in a pipeline:

~~~text
produce - ./transform.rx - consume
~~~

An incoming raw value feeds the first statement of the recipe. The final statement's raw result is the recipe's raw result.

## Physical-line continuation

A physical line beginning with -- extends the preceding operation:

~~~text
configure charger
--serial ABC123
--limit 32
--enabled
~~~

This is one logical operation equivalent to:

~~~text
configure charger --serial ABC123 --limit 32 --enabled
~~~

Use the compact one-line form when the operation and target are easy to read. Break flags onto continuation lines when that improves reviewability.

Blank lines and full-line comments are ignored.

## Recipe parameters and semantic context

Arguments supplied after a recipe path become values in the shared Gateway context before execution:

~~~text
gway ./deploy.rx --site MTY --role Watchtower --dry-run
~~~

A bare recipe flag becomes the boolean `True`; a flag followed by a value stores that token as a string. Dash-separated names normalize to underscore-style context names during recipe argument parsing. Operations may still coerce those strings normally when binding them to annotated parameters.

Recipe parameters do not create a separate lexical scope. Internal operations publish normally into the same Gateway runtime.

Mapping results publish their members into semantic context, so later operations can consume them without explicit plumbing.

Semantic mapping lookup is deliberately forgiving. Case, spaces, dashes, and underscores are equivalent:

~~~text
StatusCode
status-code
status_code
status code
~~~

Ambiguous mappings containing multiple keys that collapse to the same semantic name are errors rather than silently choosing one.

## Sigils

Sigils resolve named semantic values:

~~~text
[site]
[status_code]
[charger serial]
~~~

An inline fallback is used when the named value cannot be resolved:

~~~text
[role|Watchtower]
~~~

The fallback is part of sigil resolution rather than recipe-parameter parsing, so the same form can be used inside ordinary operation arguments.

Single quotes protect literal text from GWAY interpretation:

~~~text
echo '[site]'
~~~

Double quotes group text while retaining normal resolution behavior.

## Companion Python files

Before executing a recipe, GWAY looks for a sibling Python file with the same stem:

~~~text
recipes/
    deploy.rx
    deploy.py
~~~

If deploy.py exists, it is ingested before any recipe statement is resolved. Its public callable surface is exposed through normal path-ingestion semantics under the deploy root.

This split is intentional: the recipe remains the human-reviewable orchestration surface, while Python contains implementation detail.

A missing companion is fine. A companion import failure aborts recipe execution before the first statement. A companion path is ingested at most once per Gateway instance.

## Nested recipes

Recipes may invoke other recipes. Relative paths resolve from the directory containing the current recipe rather than from the process working directory:

~~~text
./prepare.rx
./verify.rx
~~~

Nested recipes share the caller's Gateway state, semantic context, result history, and rollback journals. Recursive recipe cycles are rejected.

Only the outer execution boundary owns automatic journal cleanup. An inner recipe can therefore open a journal that an outer recipe later validates and commits.

## Atomic check

check validates the current raw result without replacing it.

In a pipeline:

~~~text
inspect charger - check --status healthy
~~~

As a later statement, check validates the most recently published result:

~~~text
inspect charger
check --status healthy
~~~

A successful check returns the original result unchanged.

### Whole-result checks

Strict boolean checks:

~~~text
check --true
check --false
~~~

These require an actual Python bool.

Whole-result equality:

~~~text
check --is ready
check --is 200
~~~

Unquoted expected values are lightly coerced before comparison: `true` and `false` become booleans, `none` / `null` become `None`, and ordinary Python literal forms such as numbers are parsed as literals. Single quotes force string comparison, so `check --is '200'` compares against the string `"200"`.

### Mapping checks

A named flag requires a semantic mapping key to exist:

~~~text
check --ready
~~~

A flag plus a value requires semantic equality:

~~~text
check --status healthy
check --status-code 200
~~~

Multiple assertions are conjunctive.

Negative forms invert the assertion:

~~~text
check --no-error
check --no-status failed
~~~

The first requires error to be absent. The second rejects only the exact semantic pair status == failed; a missing key or a different value passes.

Because no- is control syntax, quote a flag to address a literal semantic field beginning with no-:

~~~text
check '--no-error'
check '--no-status' disabled
~~~

Quoted control-looking flags are mapping fields rather than control options. The same escape allows literal fields named rollback or unless:

~~~text
check '--rollback' armed
check '--unless' true
~~~

## Feature guards with --unless

--unless BOOL is a guard for checks that should not run when a feature is deliberately disabled:

~~~text
check --unless [feature_disabled] --status healthy --ready
~~~

The guard is evaluated before every assertion regardless of where --unless appears.

- True: skip the assertions and return the original result successfully.
- False: evaluate the assertions normally.
- non-boolean: fail the check.

Only one --unless guard is allowed, and a check still requires at least one actual assertion.

## repeat

repeat replays semantic operations rather than duplicating command text manually.

A standalone repeat replays the previous operation:

~~~text
probe
repeat
~~~

Repeat a fixed number of times:

~~~text
probe
repeat --times 3
~~~

Inside a raw pipeline, repeat replays the completed prefix of the current statement:

~~~text
fetch - transform - repeat --times 2
~~~

An explicit target can be repeated directly:

~~~text
repeat probe --times 3
~~~

Conditional forms:

~~~text
probe
repeat --until ready --max 10

probe
repeat --while pending --max 10
~~~

The gate may be a boolean-producing operation, a boolean sigil, or the literal true / false form when the replayed operation itself returns a boolean.

Optional delay between attempts applies to both fixed and conditional repeats:

~~~text
repeat --times 3 --interval 1
repeat --until ready --max 10 --interval 1
~~~

Conditional repeats default to 100 attempts when --max is omitted. Reaching the limit raises RepeatLimitError.

--times cannot be combined with --while or --until, and --while and --until are mutually exclusive.

## Rollback journals

Rollback journals make a group of supported filesystem mutations reversible.

Current rollback-aware operations include:

~~~text
copy
move
link
remove
render
~~~

Attach a journal name to each mutation in one logical transaction:

~~~text
copy new.conf /etc/app.conf --rollback deploy
render app.conf.tmpl --to /etc/app.conf --rollback deploy
~~~

The journal opens implicitly on the first recorded mutation.

Commit after validation:

~~~text
commit deploy
~~~

Or roll back explicitly:

~~~text
rollback deploy
~~~

A successful commit or rollback closes the journal and discards its stored rollback material. Commit is refused if the journal contains an unsealed `MUTATED` entry or is already in a mixed state after a partial rollback; recovery material must remain available until that rollback is resolved.

## Control-triggered rollback

check and repeat can trigger a named rollback when their terminal requirement fails:

~~~text
copy new.conf /etc/app.conf --rollback deploy
service reload
service status
check --active --status running --rollback deploy
commit deploy
~~~

or:

~~~text
copy new.conf /etc/app.conf --rollback deploy
service reload
probe health
repeat --until healthy --max 20 --rollback deploy
commit deploy
~~~

The same spelling has two context-dependent meanings:

~~~text
mutation --rollback deploy
~~~

records reversible state.

~~~text
check/repeat ... --rollback deploy
~~~

requests recovery if the control requirement ultimately fails.

Intermediate non-terminal repeat attempts do not trigger rollback. For `repeat`, the named rollback also runs if replay or gate evaluation raises; exhaustion is only one terminal failure mode. A successful check/repeat does not commit or rollback anything; the journal remains open for explicit commit.

When a check assertion or repeat execution fails, its original error remains primary. If rollback also fails, recovery failure is attached as secondary context. If a later outer-boundary retry also fails, GWAY preserves both recovery failures rather than replacing the earlier one. Invalid control syntax that fails while options are being parsed is not itself a transactional failure and does not trigger rollback.

## Execution boundaries

Nested GWAY calls and nested recipes share one outer execution boundary.

A journal may not silently escape a successful invocation. If execution finishes successfully with an open journal, GWAY attempts rollback and raises UncommittedJournalError even when recovery succeeds. This catches recipes that forgot to commit.

If execution is already failing, the boundary attempts recovery of remaining open journals while preserving the original failure as primary.

Multiple journals are recovered in reverse opening order.

If a control-triggered rollback succeeds, its journal is already gone when the boundary runs and is not rolled back twice. If recovery is incomplete, the journal remains open and the boundary may make one final recovery attempt.

## Mutation lifecycle and safety

Rollback-aware mutations use a persisted lifecycle:

~~~text
PREPARED -> MUTATED -> APPLIED -> ROLLED_BACK
~~~

PREPARED means pre-mutation state was captured.

MUTATED means the forward filesystem change completed but its post-state fingerprint has not been safely sealed.

APPLIED means the mutation and expected post-state fingerprint are persisted.

ROLLED_BACK means the recorded state was restored.

MUTATED is deliberately conservative. If post-mutation fingerprinting fails, GWAY retains the journal and refuses to blindly restore or commit that entry because it cannot prove which post-state is safe to overwrite.

Rollback is drift-aware for APPLIED entries. Unexpected external changes prevent GWAY from blindly restoring over them.

## Complete deployment pattern

A transactional recipe can remain short:

~~~text
deploy prepare

render app.conf.tmpl --to /etc/app.conf --rollback deploy
service reload app

service status app
check
--unless [service_disabled]
--active
--status running
--rollback deploy

commit deploy
~~~

For a service that needs time to converge:

~~~text
deploy prepare

render app.conf.tmpl --to /etc/app.conf --rollback deploy
service reload app

probe health
repeat --until healthy --max 20 --interval 1 --rollback deploy

commit deploy
~~~

Keep low-level retry algorithms and protocol-specific health logic inside operations. The recipe should stay a compact statement of what is being attempted, what constitutes success, and what should be rolled back if validation fails.

## Design guidance

Prefer recipes when the sequence itself is useful operational documentation, humans should review the intended steps, and operations already expose the right semantic vocabulary.

Prefer Python when the work needs arbitrary branching, implementation-specific algorithms, complex state manipulation, or reusable lower-level logic.

A useful rule is:

> If the recipe has to explain how an operation works, the operation probably needs a better semantic boundary.
