# Gway Glossary

Gway uses ordinary words with deliberately specific meanings.

The purpose of this glossary is not to define English in general, but to establish
a shared semantic vocabulary for Gway operations, recipes, adapters, and related
tooling.

A term should keep the same meaning wherever practical. Different words should
imply a meaningful distinction rather than stylistic variation.

This glossary is expected to grow gradually as distinctions become useful in real
Gway code.

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

### Example

```text
create user
create directory
create DNS-record
```

`create` remains the operation.

The subjects differ.

The mechanisms differ.

The invariant is that something appropriate to the subject exists afterward where
no such instance existed before.

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
independent semantic category to which that subject belongs.

A subject may belong to any number of topics, and those topics do not form a
semantic hierarchy. Topic membership can organize, group, and disambiguate
subjects without becoming part of the subject itself.

Prefer the smallest expression that preserves the subject's complete semantic
identity. A modifier belongs in a topic when removing it leaves the same kind of
subject and merely removes categorization or context. A modifier remains part of
the subject when removing it changes what entity the subject denotes.

For example:

```text
operation: read
subject:   log
topics:    Arthexis, remote, MCP
```

Here `Arthexis`, `remote`, and `MCP` qualify the subject without changing the
fact that the subject is a log.

By contrast:

```text
subject: API key
```

should not normally be reduced to:

```text
subject: key
topic:   API
```

because `API key` is a distinct semantic entity from a generic `key`.

See **Topic** for the complete topic model.

### Subject specialization

Subjects allow one operation to support different mechanical implementations.

Conceptually:

```text
cook rice
    -> rice-specific cooking procedure

cook steak
    -> steak-specific cooking procedure
```

The subject therefore acts as a semantic specialization point.

The important invariant is:

```text
same operation
different subject
different implementation allowed
same fundamental state transition intended
```

This is one of the central composition principles of Gway.

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

## Relationship between Operation and Subject

An operation answers:

> What kind of change or effect is being requested?

A subject answers:

> What is that operation specifically about?

Together they form one of the fundamental semantic units of Gway:

```text
operation + subject
```

For example:

```text
cook rice
create user
start service
delete file
```

The operation supplies the invariant semantic transformation.

The subject supplies enough specificity for Gway to determine how that
transformation applies in this case.

The same model also applies when one of the terms is implicit:

```text
copy [source] --to [target]
```

may semantically expand to:

```text
copy file [source] --to [target]
```

and a one-word form such as:

```text
log
```

may semantically represent:

```text
operation: log
subject:   log
```

The surface syntax may therefore contain one word, two words, or additional
arguments without changing the underlying model.

A well-defined operation should retain its meaning when its subject changes.

A well-defined subject should specialize the operation without redefining it.

And a subject that is not explicitly written must still be recoverable from the
semantics of the invocation.


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

This gives the three concepts distinct roles:

``` text
operation
    what effect is performed

subject
    what the effect is about

sigil
    what semantic value belongs here
```

A sigil therefore allows a recipe to remain specific about meaning without becoming specific about storage or concrete value.

For a more detailed explanation of Sigil syntax, see the [Sigil syntax reference](<../reference/sigil-syntax.md>).
