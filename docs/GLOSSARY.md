# Gway Glossary

Gway uses ordinary words with deliberately specific meanings.

The purpose of this glossary is not to define English in general, but to establish
a shared semantic vocabulary for Gway operations, recipes, adapters, and related
tooling.

A term should keep the same meaning wherever practical. Different words should
imply a meaningful distinction rather than stylistic variation.

This glossary is expected to grow gradually as distinctions become useful in real
Gway code.

## Semantic index

- [Operation](#operation) — a reusable semantic action or effect.
- [Subject](#subject) — the entity an operation is about.
- [Topic](#topic) — an independent category describing a subject.
- [Context](#context) — the scoped semantic state available during execution.
- [Result](#result) — the value produced by a completed operation.
- [Chain](#chain) — an ordered composition of operations that can itself act as an operation.
- [Command](#command) — the complete executable action requested by an operator.
- [Glyph](#glyph) — a syntactic character or ordered character construction with defined meaning.
- [Flag](#flag) — a subject trait matched by an operation parameter.
- [Sigil](#sigil) — a semantic reference whose concrete value is resolved from context.

## Operation

An **operation** is an effectful action that attempts to bring about a particular
kind of state or state transition.

An operation describes **what is being done**, independently of the particular
subject to which it is applied.

For example:

```text
cook rice
cook steak
```

Both commands use the same operation:

```text
cook
```

The mechanical procedure required to perform that operation may differ
substantially between rice and steak, but the semantic intent remains the same:
transform the subject into a cooked state.

Likewise:

```text
create file
create user
create database
```

may require completely different implementations, but `create` retains the same
semantic requirement: after successful execution, an instance exists that did not
exist in that relevant place or context before.

If an implementation called `create` does not bring about that kind of state
transition, then it is not semantically implementing the `create` operation.

### An operation is always verbal

An operation is always **verbal in semantic role**: it describes an action, effect,
or attempted state transition.

This does not require the token naming the operation to already be a conventional
English verb.

For example:

```text
create user
start service
cook rice
```

use words that are plainly verbal.

Other Gway words can occupy both operation and subject roles:

```text
log
check
```

English already permits both verbal and nominal readings for these words.

Some operations may use a word that is primarily nominal in ordinary English:

```text
env
```

In that case Gway gives the word an operational reading. The command is still
semantically verbal because executing it performs an effect associated with the
environment, such as exposing or constraining execution through environmental
state.

A useful naming test is therefore not merely:

> Is this word an English verb?

but:

> What does it mean to perform this operation?

If a proposed operation name cannot describe a coherent action or state
transition, it is more likely naming a subject, topic, or other semantic role than
an operation.

### Operations are effectful

A Gway operation always produces an observable effect.

The effect may involve external resources:

```text
create file
delete user
start service
```

or it may affect execution state:

```text
read log
resolve value
inspect service
```

Even when an operation primarily obtains information, its execution makes a result
available to Gway's execution context, result history, output surface, or another
observable consumer.

Gway therefore does not treat operations as pure mathematical functions.

A mathematical function can be represented abstractly as:

```text
input -> output
```

A Gway operation is closer to:

```text
subject + context + arguments + current state
    ->
result + changed observable state
```

The defining property is not merely that an operation *can* have side effects.

**Effect is part of what makes it an operation.**

### Every operation has a subject

A Gway operation never exists semantically without a subject.

The subject may be:

- written explicitly;
- inferred from another value;
- inferred from type or structure;
- implied by the operation;
- or represented by the same word as the operation.

But it is always present.

For example:

```text
copy file [source] --to [target]
```

can be understood as:

```text
operation: copy
subject:   file
source:    source
target:    target
```

If Gway can determine that `[source]` resolves to a filesystem path, the explicit word
`file` may be unnecessary:

```text
copy [source] --to [target]
```

The subject has not disappeared. It has been inferred.

Likewise, if `[source]` identifies a SQL table, the same operation might resolve
conceptually as:

```text
copy SQL [table] --to [target]
```

The operation remains `copy`, while the subject changes according to the
semantics of the supplied values.

### The operation should survive a change of subject

A useful test for an operation name is to ask whether the same semantic action
still exists when its subject changes.

For example:

```text
cook rice
cook steak
```

The procedures differ, but `cook` survives the substitution.

Similarly:

```text
start process
start service
start vehicle
```

may require different mechanisms, but each should represent the transition
associated with `start`.

If changing the supposed subject also changes what the verb fundamentally means,
the model may actually contain multiple operations that happen to share an English
word.

Operations are not topic-scoped. Topics classify subjects, not operations. An
operation remains available across any topics in which a compatible subject may
appear.

### Operation versus implementation

An operation defines semantic intent.

Its implementation defines how that intent is achieved for a particular subject.

Therefore:

```text
operation + subject
```

may select an implementation without changing the meaning of the operation itself.

This distinction allows Gway to compose operations semantically while adapters and
subject-specific implementations handle mechanical differences.

## Subject

A **subject** is the most specific semantic entity that an operation is about while
the operation itself remains unchanged.

For example:

```text
cook rice
cook steak
```

`cook` is the operation.

`rice` and `steak` are subjects.

Changing the subject may substantially change how the operation must be performed
without changing what operation is being requested.

The subject therefore provides the semantic information needed to specialize an
otherwise stable operation.

### A subject is always present

Gway does not have subjectless operations.

What may be absent is only the **explicit spelling** of the subject.

Consider:

```text
copy file [source] --to [target]
```

Here the semantic structure is explicit:

```text
operation: copy
subject:   file
source:    source
target:    target
```

But this could also be written:

```text
copy [source] --to [target]
```

if Gway already knows from the values involved that the subject is `file`.

Likewise, another invocation might imply:

```text
operation: copy
subject:   SQL
```

because `[source]` is recognized as a SQL table.

The subject is therefore part of the semantic interpretation even when no separate
subject token appears in the command.

### A single word may be both operation and subject

Some Gway operations appear as single-word commands.

This does not mean the subject has been discarded.

Instead, one word may carry both semantic roles.

For example:

```text
log
```

can naturally be interpreted as:

```text
operation: log
subject:   log
```

The English word already works both as a verb and as a noun, and the Gway
semantics can reflect that dual role.

Likewise:

```text
check
```

may mean:

```text
operation: check
subject:   check
```

until additional information specializes the subject:

```text
check service
check MCP
check arthexis
```

The important rule is:

> A one-word Gway command is not a subjectless command. The single word
> encapsulates both operation and subject unless the subject can be inferred more
> specifically from other semantics.

This allows compact commands without abandoning the operation-subject model.

### Subject inference

The explicit subject is unnecessary when the subject can be derived without
ambiguity from other semantic information.

That information may include:

```text
value type
value structure
path shape
known identity
adapter
context
other arguments
```

For example:

```text
copy /tmp/a /tmp/b
```

may allow Gway to infer:

```text
subject: file
```

while:

```text
copy users archive_users
```

in a SQL-aware context may infer:

```text
subject: SQL table
```

The operation is still `copy`.

Only the mechanism and subject specialization differ.

This is not omission of semantic information. It is **semantic compression**:
information that can already be derived does not need to be repeated.

### The subject is not the actor

In ordinary grammar, an imperative such as:

```text
set M
```

may be interpreted as having an implied actor such as "you."

Gway does not use **subject** in that grammatical sense.

The actor responsible for execution may be ambiguous or irrelevant. An operation
could have been initiated by:

- a human;
- another recipe;
- a scheduler;
- an MCP client;
- a service;
- an adapter;
- another operation;
- or some future execution mechanism.

Gway does not need to identify that actor in order to understand the command.

Instead:

```text
set M
```

is understood semantically as:

```text
operation: set
subject:   M
```

`M` is the entity about which `set` is being performed.

One can loosely think of the operation as belonging to the subject itself:

```text
M -> set
```

rather than requiring Gway to model an external agent that performs the action.

### The subject is not necessarily what changes

The subject is what the operation is **about**.

It is not necessarily the state directly modified by the operation.

For example:

```text
read log
```

may have a log source as its subject while leaving that source completely unchanged.

The observable effect may instead be the production and publication of a result.

Therefore:

**subject describes semantic focus, not necessarily mutation.**

### The subject is not a target

A **target** implies direction: something toward which an action, transfer, or
effect is directed.

A subject does not require that relationship.

For example:

```text
copy file [source] --to [target]
```

has:

```text
operation: copy
subject:   file
source:    source
target:    target
```

`file` describes what kind of thing is being copied.

`source` and `target` describe directional roles within the operation.

The subject and target may occasionally refer to the same concrete entity in some
operation, but the semantic roles remain different.

### Subject and topic

A subject is the specific semantic entity an operation is about. A topic is an
independent category that describes a subject without becoming part of its
intrinsic identity.

See [Topic](#topic) for topic membership, ordering, disambiguation, and the rule
for distinguishing topics from compound subjects.

### Subject specialization

Subjects specialize how an otherwise stable operation is implemented without
redefining that operation. See
[The operation should survive a change of subject](#the-operation-should-survive-a-change-of-subject).

### Env, environ, and environment

`env` is a useful example of one surface word carrying both an operation and a
subject, but the two semantic roles are not identical.

The full English word **environment** is historically related to **environ**:
to surround or encircle. The noun describes the surrounding conditions in which
something exists or executes.

Gway uses that distinction directly:

```text
operation: env     # semantically: environ
subject:   env     # semantically: environment
```

The operation is verbal. To `env` is to make the effective environment that
already surrounds an execution observable to Gway.

The subject is nominal. The environment is the surrounding execution state itself.

This is not equivalent to getting an environment. The environment already exists
as part of the execution context whether or not the `env` operation is invoked.
Child processes and other execution within that scope may already consume that
environment without Gway first retrieving or activating it.

Therefore:

```text
env
```

does not mean:

```text
get env
```

It means, conceptually:

```text
environ environment
```

with both roles compressed into the conventional technical spelling `env`.

Executing `env` makes the effective surrounding conditions visible as an
observable Gway result. It does not create the environment and does not make the
environment begin applying.

More specialized operations may still act upon the environment explicitly:

```text
get env [name]
set env [name] [value]
```

but those operations have different meanings from the standalone `env`
operation.

This distinction also illustrates why a one-word command is not subjectless. The
surface token can encode a verbal operation and its corresponding nominal subject
at the same time.

## Topic

A **topic** is an independent semantic category that qualifies, groups, organizes,
or disambiguates a subject without becoming part of that subject's intrinsic
identity.

Topics classify subjects. They do not classify operations.

For example:

```text
operation: read
subject:   log
topics:    Arthexis, remote, MCP
```

The subject is `log`. The topics provide additional semantic context about that
subject.

### A subject may have multiple topics

Topic membership is many-to-many.

A subject may belong to several topics at the same time:

```text
subject: log
topics:  Arthexis, remote, MCP
```

None of those topics contains the others. The subject belongs independently and
equally to each applicable topic.

Likewise, one topic may classify many different subjects.

### Topics are not hierarchical

Gway does not assign semantic meaning to a hierarchy between topics.

An implementation may use directories, modules, objects, namespaces, or another
hierarchical representation for practical reasons, but that implementation
structure does not make the topics themselves hierarchical.

Conceptually:

```text
topics: remote, MCP
```

does not mean:

```text
remote
    └── MCP
```

and it does not mean:

```text
MCP
    └── remote
```

The subject belongs to both topics independently.

Implementation structure must not leak into semantic meaning.

### Topic order must not change meaning

Topics behave semantically like an unordered set, even when an implementation
must inspect or resolve them in some order.

Therefore:

```text
remote MCP
MCP remote
```

should represent the same topic membership when they otherwise refer to the same
subject and operation.

There may be implementation-level priority rules used while searching for,
combining, or resolving implementations. Those rules are implementation details;
they must not create different semantic meanings for the same set of topics.

An architecture in which `remote MCP` implements substantially different behavior
from `MCP remote` is generally a code smell. If the two forms genuinely require
different semantics, some distinction other than topic ordering is probably
missing and should be represented explicitly.

### Topics organize, group, and disambiguate subjects

Topics provide useful context around subjects.

They can organize related subjects, associate subjects that belong to the same
semantic domain, and disambiguate a subject whose meaning would otherwise be
unclear.

For example:

```text
subject: log
topics:  Arthexis, remote
```

still describes a log. The topics tell Gway more about which log and in what
semantic context it participates.

Topics may therefore help discovery, adapters, recipes, documentation, or
implementation selection without becoming part of the subject itself.

### Prefer the smallest semantically complete subject

Subjects should usually be expressed as the smallest term that preserves their
complete semantic identity.

For example:

```text
subject: log
topic:   Arthexis
```

is preferable to treating `Arthexis log` as a compound subject when `Arthexis`
only categorizes whose or which domain's log is involved.

This is not a rule that subjects must contain one word.

A compound expression remains a single subject when the compound itself names a
distinct semantic entity:

```text
subject: API key
```

An `API key` is not merely a generic `key` placed under an `API` topic if
removing `API` changes what entity the subject denotes.

A useful test is:

> A modifier belongs in a topic when removing it leaves the same kind of subject
> and merely removes categorization or context. A modifier remains part of the
> subject when removing it changes the subject's semantic identity.

### A subject is not implicitly listed as its own topic

A subject can trivially be understood as belonging to a category named after
itself, but that relationship is normally tautological.

For example:

```text
subject: log
topic:   log
```

is logically possible, but it usually adds no useful semantic information. The
subject already establishes that the operation is about a log.

Gway therefore does not treat every subject as implicitly having a same-named
topic, and implementations should not manufacture such topic membership merely
because it is technically true.

Topics should contribute semantic information beyond the identity already supplied
by the subject.

This is not an absolute prohibition. The same word may legitimately occur as both
subject and topic when those roles arise independently and the topic membership
has semantic value. The rule is not to create topic membership merely by repeating
the subject.

### Topics classify subjects, not operations

Operations are never grouped into topics.

An operation describes an action or effect that may be meaningful across many
different subjects:

```text
read log
read file
read socket
read configuration
```

The operation remains `read`.

Each subject may belong to its own set of topics, but `read` itself is not a
member of those topics.

For example:

```text
operation: read
subject:   log
topics:    Arthexis, remote
```

and:

```text
operation: read
subject:   file
topics:    configuration, local
```

use the same operation in different semantic contexts.

Grouping `read` under any of those topics would incorrectly suggest that the
operation is limited to that domain. An operation should apply to any subject for
which its semantic effect is coherent.

A useful invariant is:

> Subjects may belong to topics. Operations do not.

### Topic membership is semantic, not structural

A topic should be assigned because a subject meaningfully belongs to that category,
not merely because its implementation happens to live inside a particular module,
directory, class, or object.

For example, an implementation layout might contain:

```text
remote/
    mcp/
        ...
```

That structure may be convenient, but semantically it should still be understood
as:

```text
topics: remote, MCP
```

rather than as a topic path.

If the implementation were reorganized as:

```text
mcp/
    remote/
        ...
```

the semantic interpretation should remain unchanged.

A useful invariant is:

```text
same operation
same subject
same set of topics
different topic ordering or implementation layout
same semantic meaning
```

## Context

**Context** is the semantic state available around the execution of a Gway command.

It contains information that is not necessarily written directly into the command
but may still participate in interpreting or executing it.

For example, an earlier operation or recipe invocation may establish:

```text
--site MTY
```

Later, a command containing:

```text
[site]
```

may resolve that semantic value without requiring `MTY` to be repeated.

Context therefore allows Gway to carry semantic information across operations
without forcing every command to restate everything it already knows.

### Context is ambient semantic state

Context surrounds an operation rather than being one of its intrinsic semantic
parts.

A command may explicitly provide an operation, subject, flags, sigils, values, and
glyphs while context supplies additional semantic facts already available when
that command executes.

Conceptually:

```text
command
    executes within
context
```

The command expresses what should happen.

The context supplies relevant semantic information already known to Gway.

### Context can satisfy unresolved meaning

Sigils are one of the clearest consumers of context.

For example:

```text
[domain]
```

asks Gway to resolve the semantic meaning `domain`.

If the current context was established with:

```text
--domain remote.example.com
```

then the sigil may resolve to:

```text
remote.example.com
```

without that concrete value being hard-coded into the command.

### Context can participate in binding

Context is not limited to explicit sigil resolution.

Suppose an operation accepts the flag:

```text
--site
```

and the active context already contains a semantic value established through:

```text
--site MTY
```

Gway may use that contextual value to satisfy the operation's `site` parameter
when no more specific value has been supplied.

This works because the flag name carries semantic meaning shared between the
operation, its subject, and the surrounding context.

The information has not disappeared. It has become ambient.

### Context names are semantic

A context name is not intended to be an arbitrary variable name used merely to
move data between operations.

The identifier itself should describe a stable semantic meaning.

For example:

```text
--site MTY
```

does not merely create a conveniently named variable called `site`.

It establishes a semantic fact whose meaning is `site`.

Other operations and subjects that understand the same flag are expected to
interpret that meaning consistently.

A useful rule is:

> Shared context names should imply shared semantic meaning.

Context therefore behaves differently from an ordinary collection of temporary
programming variables.

### Context has scope

Context is not one flat global namespace.

A semantic value may exist at different execution scopes, and the scope in which a
value is introduced determines where that value is visible.

For example, if a command supplies:

```text
inspect charger --site MTY
```

then `--site MTY` belongs to that operation invocation unless something
explicitly publishes it into a broader scope.

The operation may consume the value while it executes, but the surrounding
container does not automatically acquire it merely because one child operation
received it.

### More specific scope overrides broader scope

When the same semantic name exists at several scopes, the nearest applicable value
wins.

For example, suppose the surrounding container has:

```text
--site MTY
```

and one operation is invoked with:

```text
deploy service --site GDL
```

Then the operation sees:

```text
--site GDL
```

while the surrounding container continues to hold:

```text
--site MTY
```

after the operation completes.

Conceptually:

```text
operation-local context
    overrides
container context
    overrides
more external context
```

A useful principle is:

> Specific semantic information overrides more ambient semantic information.

### Context does not propagate outward automatically

Context inheritance is normally inward.

A child operation may consume semantic values available from its parent or
container scope.

The reverse is not automatic.

Values introduced inside an operation do not become part of the surrounding
context merely because they existed during that invocation.

A useful rule is:

> Context flows inward by visibility, but outward only by publication.

### Operations may deliberately publish context

An operation may explicitly publish some or all of the context it receives into
the surrounding container scope.

Publication is therefore an operation behavior, not the default behavior of
context itself.

For example, an operation might receive:

```text
--site MTY
--role Watchtower
```

and deliberately publish those semantic values outward.

After publication, following operations in the containing scope may consume them
without those values being written again.

### `default` publishes context

The `default` operation is the canonical example of deliberate context
publication.

It accepts semantic context and publishes that context back into the containing
scope.

For example:

```text
default --site MTY --role Watchtower
```

establishes those values as defaults available to later operations in the
containing execution scope.

For example:

```text
default --site MTY

inspect charger
deploy service --site GDL
verify charger
```

may be understood as:

```text
container context:
    --site MTY

inspect charger
    sees --site MTY

deploy service --site GDL
    sees --site GDL

verify charger
    sees --site MTY
```

The explicit value supplied to `deploy` overrides the default only for that
operation.

The surrounding context remains unchanged.

### Publication and return values are different

Publishing context outward is not the same as returning a result.

An operation may return a raw result, publish semantic context, do both, or do
neither.

A pipeline may carry a raw result to the next operation while context publication
makes named semantic values available more broadly.

These are separate effects.

### Context scopes compose

Because context is scoped, nested execution can safely specialize semantic values.

Conceptually:

```text
outer context
    --site MTY

    recipe context
        --role Watchtower

        operation context
            --site GDL
```

The innermost operation sees the most specific applicable values while broader
scopes retain their own values unless publication explicitly changes them.

A useful invariant is:

> Context is inherited inward, overridden locally, and published outward only
> deliberately.

### Context is not the raw pipeline

A pipeline transfers a particular raw result between connected operations.

Context carries named semantic state.

For example:

```text
produce - consume
```

uses the pipeline glyph to transfer the previous raw result positionally.

By contrast:

```text
produce
consume
```

may still allow `consume` to use semantic values published by `produce`
through context even though the raw result is not transferred positionally.

A useful distinction is:

```text
pipeline
    transfers a raw value through an ordered chain

context
    carries named semantic state across execution
```

### Context is semantic, not merely structural

Context follows Gway's semantic naming rules.

For example:

```text
--status-code 200
```

may correspond semantically to representations such as:

```text
status-code
status_code
status code
```

where Gway's identifier normalization makes that relationship unambiguous.

The important fact is not the exact storage spelling. It is that all of those
forms identify the same semantic concept.

### Context is not environment

Context and environment may both provide values during execution, but they are
different concepts.

The **environment** is part of the surrounding process or execution environment.

The **context** is Gway's semantic execution state.

Environment values may participate in semantic resolution, but the environment
and context should not be treated as the same namespace.

### Context is not storage

Context should not be understood as a particular dictionary, object, database, or
other storage implementation.

Those may be mechanisms used to hold context.

The semantic concept is broader:

```text
context
    the semantic facts currently available to execution
```

Its implementation may change without changing what context means.

### Context enables semantic compression

One of the main purposes of context is to avoid repeating information that Gway
already knows.

If `--site MTY` has already been established semantically, later operations that
share the meaning of `--site` may reuse it.

This is another form of **semantic compression**:

> Information that is already available unambiguously does not need to be written
> again.

Explicit information remains free to override it whenever the current command
needs a different value.

### Context belongs to execution, not to an operation

An operation may consume context or publish into context, but context does not
belong exclusively to that operation.

It surrounds the execution in which multiple operations may participate.

A useful invariant is:

> Operations act within context; the nearest applicable semantic value wins.

## Result

A **result** is the value produced by a completed Gway operation.

For example:

```text
read charger
```

may produce a charger object as its result.

The result is the direct product of performing the operation. It is not itself
the operation, the subject, or the surrounding context.

Conceptually:

```text
operation
    acts upon
subject

operation
    produces
result
```

### Every completed operation may produce a result

An operation may produce any value appropriate to its semantics.

A result may therefore be:

```text
a scalar
an object
a mapping
a sequence
an iterator
a boolean
None
```

or any other value that the operation legitimately returns.

Gway does not require all results to have the same shape.

The meaning of a result follows from the operation and subject that produced it.

### A result is associated with its subject

When an operation has a semantic subject, Gway may retain the result under that
subject.

For example, if:

```text
get charger
```

produces:

```text
CHG001
```

then the semantic relationship is:

```text
subject: charger
result:  CHG001
```

That association allows later operations that understand the same subject to
reuse the result semantically.

A result therefore carries more meaning than merely occupying a position in a
list of returned values.

Its producing subject can remain relevant to subsequent Gway resolution.

### Results have history

Gway preserves completed results chronologically.

Conceptually:

```text
operation A -> result A
operation B -> result B
operation C -> result C
```

creates a result history:

```text
result A
result B
result C
```

The most recently produced value is the current or last result.

Result history allows later Gway semantics to refer to earlier produced values
without requiring the operations that created them to execute again.

### The last result is not the same as context

The most recent result and the active context are distinct forms of execution
state.

A result answers:

> What value did an operation produce?

Context answers:

> What semantic facts are currently available to execution?

An operation may produce a result without publishing any new context.

Likewise, an operation may deliberately publish context while returning a result
that means something else.

### Results can flow through chains

A result may become the positional input to another operation when a chain
connects them.

For example:

```text
produce - consume
```

means that the result produced on the left participates as positional input to the
operation on the right.

Conceptually:

```text
produce
    -> result
        -> consume
```

This is raw result flow.

It is distinct from semantic context resolution.

Without the connecting glyph, the raw result is not automatically transferred
positionally merely because one operation happened before another.

### A pipeline carries results, not context

The pipeline glyph connects operations through their results.

For example:

```text
find charger - inspect
```

can pass the charger result from `find` into `inspect`.

The surrounding context may also be visible to both operations, but it is not what
the pipeline glyph transfers.

A useful distinction is:

```text
result
    a value produced by an operation

pipeline
    an ordered connection that transfers a result

context
    scoped semantic state available during execution
```

### A result can be published

After an operation completes, Gway may **publish** its result.

Publication makes the completed value available to later Gway execution according
to its semantic identity.

For a subject such as:

```text
charger
```

publication may establish:

```text
subject: charger
result:  <charger value>
```

for later semantic reuse.

Publication does not change what the result is.

It changes where and how that result becomes available after it has been produced.

### Mapping results can also contribute context

A result may contain named semantic information.

For example, an inspection operation might produce a mapping equivalent to:

```text
serial: ABC123
online: true
site: MTY
```

The mapping remains the operation's result as a whole.

Its members may additionally be published into semantic context so later operations
can consume meanings such as:

```text
--serial ABC123
--online
--site MTY
```

These are two related but distinct effects:

```text
result
    the mapping produced by the operation

context publication
    semantic facts made available from that mapping
```

The result should not be understood as disappearing merely because some of its
contents become context.

### Publishing a new result may replace a subject's current result

A subject can produce multiple results over time.

For example:

```text
inspect charger
inspect charger
```

may produce two different charger results.

Both can remain part of chronological result history, while the most recently
published result associated with the `charger` subject becomes the current
semantic result for that subject.

This gives Gway both:

```text
history
    what was produced over time

subject binding
    the current result associated with a semantic subject
```

### A result can retain semantic identity through a chain

When Gway knows the subject associated with a result, that semantic identity can
help resolve the next operation.

For example, a pipeline may carry a concrete charger object while Gway also knows:

```text
subject: charger
```

A following operation can then be interpreted against the `charger` subject
without requiring the caller to redundantly spell that subject again when the
meaning is unambiguous.

The raw value and its semantic identity therefore complement one another:

```text
result value
    what was produced

result subject
    what that value semantically represents
```

### A result is not necessarily persistent

Results belong to execution state.

They are not automatically durable data, configuration, or cache entries.

Producing a result does not imply that Gway should persist it across unrelated
executions.

If a result needs durable storage, that must be an explicit semantic effect of an
operation or subsystem designed to provide it.

### A result is not an effect

An operation may have effects beyond its returned value.

For example:

```text
delete file
```

may modify the filesystem and also return a result describing what happened.

The filesystem mutation is an effect.

The returned value is the result.

These concepts should not be conflated:

```text
effect
    what execution changes or makes observable

result
    the value execution produces
```

### Result and publication are separate concepts

A result exists because an operation produced a value.

Publication determines how that value participates in subsequent Gway execution.

Conceptually:

```text
operation
    -> result
        -> publication
            -> result history
            -> subject association
            -> possibly semantic context
```

An implementation may deliberately suppress or specialize publication without
changing the semantic fact that results and publication are separate stages.

A useful invariant is:

> An operation produces a result; publication determines what Gway remembers
> about it.

## Chain

A **chain** is an ordered sequence of connected operations whose outputs, context,
or execution semantics cause them to participate in one larger action.

For example:

```text
produce - transform - consume
```

contains three operations connected into one chain.

Each operation retains its own semantic identity, but their composition also has
meaning as a whole.

### Chains are ordered

A chain is always interpreted from left to right.

The order of its operations is part of its semantic meaning.

For example:

```text
read - transform - write
```

is not equivalent to:

```text
write - transform - read
```

even if both expressions contain the same operations.

This distinguishes chains from semantic structures whose components may be
unordered. Topics, for example, behave semantically like a set. Their ordering
should not change meaning.

A chain behaves differently:

```text
A - B - C
```

means that `A` precedes `B`, and `B` precedes `C`.

Reordering those elements produces a different chain.

### A chain is a composite operation

A completed chain can itself be understood as an operation.

Conceptually:

```text
operation A
    -> operation B
    -> operation C
```

forms:

```text
composite operation ABC
```

This does not erase the operations inside the chain.

It means that, from outside the chain, the complete ordered composition can be
treated as one action with its own input, effect, and result.

This property allows chains to compose recursively. A chain may therefore
participate wherever an operation can meaningfully participate, and a larger chain
may contain another composite chain without requiring callers to understand its
internal implementation.

### Connections define the chain

Operations do not form a chain merely because they appear near one another.

They form a chain because Gway connects their execution through defined glyphs and
semantic rules.

For example:

```text
produce - consume
```

uses the pipeline glyph to transfer the previous raw result into the next
operation.

Other connective forms may preserve semantic context or establish another defined
relationship between adjacent operations.

The glyph determines how the operations are connected. Their left-to-right order
determines when those connections apply.

### Chains preserve operation semantics

Composition should not redefine the individual operations inside a chain.

If:

```text
read
transform
write
```

have established meanings independently, then:

```text
read - transform - write
```

should preserve those meanings while adding the semantics of their ordered
connection.

The chain expresses a larger action by composing operations, not by redefining
them.

### A chain has a boundary

A chain can be treated as a unit once its composition is complete.

From outside that boundary, callers may care about:

```text
input
effect
result
```

without needing to know every internal stage.

This is what allows a recipe, embedded Gway call, or another chain to consume the
result of a chain as though it came from one operation.

A useful invariant is:

> A chain is internally plural but externally singular.

It contains multiple ordered operations, yet the completed chain can itself
participate as one composite operation.

## Command

A **command** is a complete description of an action that an operator asks Gway to
perform upon the system Gway is operating on or managing.

A command may consist of one fully described operation or of an ordered chain of
such operations.

Conceptually:

```text
command
    = complete operation
      or
      ordered chain of complete operations
```

### A command fully describes an intended action

An operation by itself identifies the kind of effect being requested.

A command provides the semantic and syntactic information necessary to express the
actual action Gway should perform.

That description may include:

```text
operation
subject
topics
flags
sigils
identifiers
values
glyphs
```

as required by the particular invocation.

For example:

```text
read log --tail 20
```

is a command containing an operation, a subject, and a flag with a value.

A more complex command may contain a chain:

```text
read log --tail 20 - filter error - print
```

The chain contains several operations, but the complete expression remains one
command because it describes one composite action requested of Gway.

### A command is not tied to the command line

A command is a Gway semantic and syntactic unit, not a concept owned by the shell
or terminal.

The CLI is one interface through which commands may be supplied, but it is not what
defines them.

Gway is designed so that every valid command can be expressed through the CLI.

For example:

```text
gway read log --tail 20 - filter error - print
```

is a textual CLI representation of a Gway command.

The command itself is:

```text
read log --tail 20 - filter error - print
```

rather than the fact that it happened to arrive through a command-line process.

### Gway interfaces share one command language

Gway expects the same command syntax and semantics to be usable through every
interface that accepts Gway commands.

The same command should therefore be transportable through interfaces such as:

```text
CLI
recipes
Python
MCP
remote execution
embedded Gway runtimes
```

without requiring each interface to invent its own command language.

Conceptually:

```text
same command
    -> CLI
    -> recipe
    -> Python
    -> MCP
    -> remote interface
```

should preserve the same Gway meaning.

An interface may package, transport, quote, serialize, or invoke that command
differently, but once Gway receives it, the command should be interpreted using
the same language.

This provides an important invariant:

> Gway has one command language and multiple interfaces.

The CLI is therefore not a special dialect. It is the most direct textual surface
for the same command syntax used throughout Gway.

### Every command should be CLI-expressible

Even when a command originates through another interface, Gway should preserve a
CLI-expressible form for it.

This gives the command language a concrete and inspectable textual representation.

A command received remotely or constructed programmatically should not require
semantics that cannot also be represented using ordinary Gway command syntax.

This keeps commands portable, inspectable, reproducible, and documentable across
interfaces.

### The operator supplies the command

The **operator** is whatever initiates the action.

That may be:

```text
a person
a recipe
another application
an MCP client
a scheduler
another Gway operation
```

The identity or nature of the operator does not redefine the command.

The important relationship is:

```text
operator
    requests

command
    which describes

action
    performed through Gway

system
    upon which that action operates
```

### Command versus operation

An **operation** describes a reusable kind of effect.

A **command** describes a particular action to perform.

For example:

```text
copy
```

names an operation.

But:

```text
copy file [source] --to [target]
```

is a command because it supplies the semantic structure needed to request a
particular use of that operation.

Likewise:

```text
produce - transform - consume
```

is a command whose primary operation is composite.

A useful distinction is:

```text
operation
    a reusable semantic action

chain
    an ordered composition of operations that can itself act as an operation

command
    the complete action requested by an operator
```

### Commands are the executable semantic unit

A command brings Gway's semantic and syntactic pieces together into something
executable. See the [Semantic index](#semantic-index) for the roles of the
individual concepts.

## Glyph

A **glyph** is a character or ordered sequence of characters that carries a
specific syntactic or semantic meaning in Gway.

A glyph is defined by the complete construction Gway recognizes, including
whitespace when whitespace participates in distinguishing one construction from
another.

For example:

```text
[ ... ]
 - 
--flag
-- 
```

These are distinct constructions even when they reuse some of the same characters.

### Glyphs may contain multiple characters

A glyph does not have to be one character long.

For example, the standalone dash used between operations is recognized as a
different construction from a dash used inside an identifier, and `--flag` is
different from a bare `--` followed by whitespace.

The exact order and boundaries of the characters are part of the glyph.

### Operative glyphs

An **operative glyph** is a glyph that causes Gway to perform a specific parsing,
resolution, composition, or execution action.

When Gway recognizes an operative glyph, that construction is interpreted
according to Gway semantics rather than passed through as ordinary data.

For example:

```text
[site]
```

uses bracket glyphs to introduce sigil semantics.

Likewise:

```text
producer - consumer
```

uses the standalone dash construction to transfer the previous raw result into the
next operation.

Anything outside Gway's defined operative glyph vocabulary remains available for
ordinary identifier or value interpretation.

### Glyph boundaries are significant

Whitespace may participate in the identity of a glyph.

For example:

```text
--flag
```

and:

```text
-- 
```

are different constructions.

In `--flag`, the double dash introduces the immediately following identifier as a
flag.

A bare `--` followed by whitespace is an end-of-options boundary. Material after
it is positional even when it begins with `--`. In recipes, a bare `--` at the
end of a physical line also causes the next substantive line to continue the same
logical operation as positional input.

### Whitespace is contextually operative

Whitespace normally separates lexical elements.

When whitespace is not already part of another recognized glyph, Gway may use it
as a semantic separator and may treat equivalent separator forms alike when doing
so is unambiguous.

This is why ordinary spaces can participate in semantic names without requiring
the implementation representation to use the same spelling.

Whitespace must not silently introduce a stronger interpretation when more than
one semantic reading remains possible.

### Connective glyphs

A **connective glyph** joins components of an identifier without introducing a new
semantic role.

The single dash and underscore are connective glyphs when they occur inside an
identifier:

```text
remote-service
remote_service
```

In identifier semantics, Gway treats spaces, dashes, and underscores as equivalent
separators when that normalization is unambiguous.

This does not make every dash equivalent to an underscore.

For example:

```text
producer - consumer
```

contains the standalone operative dash glyph and therefore has pipeline semantics.

### Identifier construction

An **identifier** is a sequence of non-operative glyphs occupying a naming role.

Connective glyphs may participate in an identifier without creating a new semantic
element.

For example:

```text
status-code
status_code
status code
```

may denote the same semantic identifier.

An operative glyph instead changes how the surrounding identifiers are
interpreted.

For example:

```text
--recursive
```

contains a flag-introducing glyph followed by the identifier `recursive`, while:

```text
[site]
```

uses bracket glyphs to make the identifier `site` a semantic reference.

### Sigils are built from glyphs and identifiers

A sigil can be understood lexically as one or more identifiers made operative by
the sigil glyphs.

For example:

```text
[site]
```

contains the identifier `site` inside the bracket construction.

Likewise:

```text
[charger serial]
```

contains semantic identifiers whose relationship is interpreted according to
sigil rules.

The glyphs provide syntax. The identifiers provide semantic names.

### Canonical glyph reference

The glossary is the canonical user-facing inventory of Gway glyphs. The inventory
must remain synchronized with the active parser and recipe grammar.

The current vocabulary includes:

| Glyph | Class | Meaning |
| --- | --- | --- |
| `[ ... ]` | operative | Forms a sigil and requests semantic resolution of its contents. |
| `[[ ... ]]` | operative | Escapes sigil interpretation and yields one literal pair of brackets. |
| `|` inside a sigil | operative | Separates a sigil lookup from its fallback value. |
| `[N]` | operative | Selects a numbered value from the current pipeline-result snapshot where chain selectors are accepted. |
| `[*]` | operative | Inserts the remaining values from the current pipeline-result snapshot where chain selectors are accepted. |
| `--identifier` | operative | Introduces an identifier as a flag or named operation parameter. |
| `--no-identifier` | operative | Negates the corresponding boolean flag. |
| bare `--` followed by whitespace/end | operative | Ends flag parsing; subsequent material is positional. At a recipe physical-line boundary it also continues the next substantive line positionally. |
| standalone `-` surrounded by token boundaries | operative | Transfers the previous raw result positionally into the next pipeline stage. |
| standalone `;` | operative | Ends a statement while preserving named semantic context and not transferring the previous raw result positionally. |
| newline in a recipe | operative | Begins a new statement unless physical-line continuation applies. |
| `-` inside an identifier | connective | Connects identifier components; semantically equivalent to underscore/space normalization in identifier lookup. |
| `_` inside an identifier | connective | Connects identifier components; semantically equivalent to dash/space normalization in identifier lookup. |
| whitespace | contextual | Separates lexical elements and may participate in equivalent semantic identifier forms when unambiguous. |
| `:` | glyph | Recognized as a distinct glyph when a grammar or value gives it meaning; otherwise it remains ordinary data. |
| `,` | glyph | Recognized as a distinct glyph when a grammar or value gives it meaning; otherwise it remains ordinary data. |
| single quotes `'...'` | operative quoting | Protect enclosed text as literal data from normal Gway structural interpretation. |
| double quotes `"..."` | operative quoting | Groups enclosed text while retaining normal Gway resolution behavior. |
| `\\` inside double quotes | operative quoting | Escapes the following character during tokenization. |

This inventory describes the active lexical surface rather than claiming that every
punctuation character is globally operative. A character such as `:` or `,` may
be a glyph without being an operative glyph in every context.

A useful compatibility rule is:

> Gway syntax is defined positively by documented operative glyphs. Characters and
> constructions outside that operative vocabulary remain ordinary input unless
> another documented grammar gives them meaning.

## Flag

A **flag** is a semantic value that is simultaneously:

```text
a parameter of an operation
and
a trait of a subject
```

When those two meanings correspond, Gway can expose that semantic relationship as
a flag.

For example, an operation may accept `path` as a parameter because the operation
needs to know how to treat the subject with respect to a path.

At the same time, the subject may meaningfully possess `path` as one of its
traits.

The matching concept can therefore be represented as:

```text
--path
```

The flag is not merely command-line syntax. It represents a semantic relationship
between an operation and its subject.

### A flag is an operation parameter

From the perspective of the operation, a flag supplies information needed to
specialize how the operation should be performed.

Conceptually:

```text
operation(subject, flag=value)
```

For example, `--path` may tell an operation that path-oriented behavior should
apply.

The operation defines what accepting that parameter means.

### A flag is a subject trait

From the perspective of the subject, the same concept describes a characteristic
that the subject possesses, supports, or can meaningfully be treated as having.

Conceptually:

```text
subject
    trait: path
```

The subject therefore provides the semantic reason that the parameter makes sense.

A parameter with no meaningful relationship to the subject is merely an
implementation argument. A subject trait that no operation can use is merely
descriptive metadata.

A flag arises when the two meanings meet.

### Flags are smaller semantic units

A flag normally represents a distinction that is not substantial enough, in the
current invocation, to stand as the operation or subject by itself.

It qualifies how an existing operation applies to an existing subject.

This does not mean that the same word can never be an operation or subject
elsewhere.

For example, `path` can be an operation:

```text
path [value]
```

where the semantic effect is to interpret or convert some value into a path.

It can also be a subject:

```text
inspect path
```

where `path` identifies the entity being inspected.

And it can be a flag:

```text
some-operation some-subject --path
```

when `path` describes a trait of the subject that is also accepted as a parameter
by the operation.

The semantic role depends on how the concept participates in the invocation.

### A flag qualifies rather than replaces

A flag does not replace the operation or the subject.

For example:

```text
operation: inspect
subject:   file
flag:      path
```

still has `inspect` as its operation and `file` as its subject.

The flag contributes an additional semantic characteristic that affects how that
operation applies to that subject.

A useful distinction is:

```text
operation
    what effect is requested

subject
    what entity the effect is about

flag
    what trait of the subject the operation should consider
```

### A bare flag means true

Flags always have a truth interpretation.

Writing a flag by itself assigns that flag the value `true`.

For example:

```text
--recursive
```

means:

```text
recursive = true
```

There is no need to write:

```text
--recursive true
```

when the intended value is simply true.

The presence of the flag is sufficient.

### Flags can be negated

A flag may be explicitly negated by prefixing the flag name with `no-`.

For example:

```text
--no-recursive
```

means:

```text
recursive = false
```

This is the explicit negative counterpart of:

```text
--recursive
```

which means:

```text
recursive = true
```

The positive and negative forms refer to the same semantic flag. They do not
define two different flags.

### Flags may carry values

A flag is not limited to boolean values.

The bare form expresses truth:

```text
--timeout
```

but a flag may also provide a more detailed value when the semantic distinction
requires one:

```text
--timeout 30
--format json
--path /srv/app
```

The supplied value refines the same semantic trait.

Conceptually:

```text
--flag
```

means:

```text
flag = true
```

while:

```text
--flag value
```

means:

```text
flag = value
```

and:

```text
--no-flag
```

means:

```text
flag = false
```

Thus every flag has a boolean interpretation, while some flags additionally admit
more specific values.

### Flags should express meaningful traits

Flags should not be created merely because an implementation happens to expose a
boolean, keyword argument, configuration field, or CLI option.

A useful Gway flag should correspond to a meaningful trait of the subject that the
operation can consume.

A useful test is:

> Does this concept describe something meaningful about the subject, and does the
> operation accept that same concept as a parameter?

If both are true, the concept is a strong candidate for a flag.

If only the operation cares about it, it may merely be an implementation
parameter.

If only the subject possesses it, it may merely be a trait.

A flag is the semantic correspondence between the two.

See the [Semantic index](#semantic-index) for how flags relate to the other core
Gway concepts.

## Sigil

A **sigil** is a symbolic semantic reference that identifies a meaning to be resolved from the execution context.

A sigil specifies **what a value means**, not where that value is stored.

For example:

``` text
[site]
[domain]
[charger serial]
```

Each expression identifies a semantic value that Gway must resolve when the operation executes.

### A sigil is not a variable

A variable normally identifies a named storage location.

A sigil identifies semantic meaning.

For example:

``` text
[site]
```

does not mean:

> read the variable named `site`

It means:

> resolve the value that currently satisfies the semantic meaning `site`

That value may come from context, environment, configuration, a previous operation, an adapter, or another supported source.

The source may change without changing the meaning of the sigil.

A useful distinction is:

``` text
variable
    names storage

sigil
    identifies meaning
```

### Why Gway calls it a sigil

The word **sigil** comes from Latin *sigillum*, meaning a small sign, mark, or seal.

Historically, a sigil is a compact symbol that stands for an identity, name, intention, or meaning without being the thing itself.

Gway uses the word in that sense.

``` text
[domain]
```

is not the domain itself. It is a sign that says:

> the semantic value of `domain` belongs here

Resolution later supplies the concrete value.

This makes sigils especially useful in recipes, where the author often knows the role a value must play before knowing what concrete value will satisfy that role during execution.

### The complete expression is the sigil

In Gway, the whole expression is the sigil:

``` text
[site]
```

The brackets are the syntax that marks the expression as a semantic reference.

This differs from languages where a sigil is only a prefix character used to mark a variable or indicate its type.

Gway sigils primarily communicate semantic identity, not storage type or value type.

### Sigils resolve at execution time

A sigil remains symbolic until Gway resolves it against the current execution context.

For example:

``` text
https://[domain]/mcp
```

contains literal text:

``` text
https://
/mcp
```

and one semantic reference:

``` text
[domain]
```

At execution time, Gway may resolve it to:

``` text
https://remote.example.com/mcp
```

The recipe specifies what belongs in that position without hard-coding where the value must come from.

### Sigils may identify structured meaning

A sigil can represent more than a single flat name.

For example:

``` text
[charger serial]
```

identifies `serial` within the semantic value identified by `charger`.

Nested sigils can make part of that semantic path dynamic:

``` text
[chargers [index]]
```

Here `[index]` is itself resolved before it participates in resolving the outer sigil.

This is another reason sigils should not be understood merely as variable substitution.

### Sigils may carry fallbacks

A sigil may provide a fallback value:

``` text
[role|Watchtower]
```

This means:

> resolve `role`; if no value can be resolved, use `Watchtower`

The fallback is part of sigil resolution rather than a separate recipe parameter mechanism.

### Sigils express unresolved semantic roles

Sigils are particularly useful for values whose semantic role is known but whose concrete value is supplied later.

For example:

``` text
copy file [source] --to [target]
```

has:

``` text
operation: copy
subject:   file
sigil:     [source]
sigil:     [target]
```

`copy` and `file` are already semantically resolved in the expression.

`[source]` and `[target]` identify meanings whose concrete values must still be supplied or discovered.

See the [Semantic index](#semantic-index) for the relationship between sigils and
the other core Gway concepts.

A sigil therefore allows a recipe to remain specific about meaning without becoming specific about storage or concrete value.

For a more detailed explanation of Sigil syntax, see the [Sigil syntax reference](<../reference/sigil-syntax.md>).
