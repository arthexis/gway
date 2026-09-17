# GWAY Semantic Recipe Language

This document captures the long-term language goals for GWAY recipes. It is intentionally aspirational: some constructs are not implemented yet.

The core idea is:

> A GWAY recipe should describe a short sequence of meaningful operations, not the low-level mechanics used to perform them.

Recipes are intended to be readable by operators, reviewable before execution, explainable at progressively deeper levels, and stable across changes in concrete implementations.

## Recipes are operational language, not general-purpose programs

A cooking recipe says `whisk until smooth`; it does not describe hundreds of wrist movements. GWAY recipes should work the same way.

- `.rx` composes named operations into human-reviewable intent.
- `.py` contains algorithms, protocol details, loops, branching, retries, polling, and implementation complexity.

Recipes should resist growing general-purpose `for`, `while`, deeply nested `if`, shell escape, or arbitrary scripting constructs. If a repeated or complex procedure appears often enough, it should normally acquire a semantic name and become an operation.

A useful rule is:

> If a recipe needs to explain how an operation works, the vocabulary may be missing a verb.

## Names carry semantic weight

Operation names should eventually participate in the semantic contract of the language.

A verb is not merely a label for one implementation. It names a family of operations that share traits. For example, implementations of `inspect` should conform to a common semantic model, conceptually similar to:

```text
Inspect[T]
    effect = READ
    mutates_target = false
    idempotent = true
    returns = Observation[T]
```

Different domains may provide different implementations:

```text
charger inspect
network inspect
service inspect
certificate inspect
```

but each should still satisfy the `Inspect` contract.

The same idea can eventually apply to verbs such as `diagnose`, `verify`, `start`, `stop`, `restart`, `recover`, `configure`, `install`, `remove`, `deploy`, `enroll`, and `sync`.

The exact ontology is not fixed here. The important goal is that names can eventually impose machine-checkable expectations about effects, result shape, idempotence, reversibility, target type, allowed nested operations, risk, or authorization class.

## One verb may resolve to many implementations

A critical GWAY goal is that one semantic operation can resolve to different concrete implementations according to target and context.

Conceptually:

```text
verb + object + context -> best valid realization of the same semantic operation
```

rather than:

```text
command name -> one hard-coded function
```

For example, `inspect charger` might resolve to OCPP for one charger, a Wire-local adapter for another, or a future protocol adapter for another. The recipe should not change when the intent is unchanged.

Resolution should build on GWAY's existing direction: names, interfaces, types, structure, context, adapters, and deterministic matching. Semantic operation identity should eventually become another invariant used by the resolver.

If no valid realization exists, GWAY should report a resolution failure rather than silently choosing a semantically different action whose signature merely fits.

## Context should remove redundant nouns

Recipes should derive operations from context where resolution is deterministic and unambiguous.

For example:

```text
charger inspect
recover
verify
```

may allow `recover` and `verify` to apply to the charger already established in context, instead of repeating `charger` on every line.

Ambiguity must remain an error or require explicit disambiguation. Context inference should improve readability, never make resolution mysterious.

## `*` means the previously selected result set

The asterisk is intended as a concise way to apply an operation to the result set selected by the previous operation.

```text
chargers find --state faulted
diagnose *
recover *
verify *
```

This is related in spirit to result insertion around Sigils: the operation consumes the relevant value selected immediately before it rather than requiring it to be restated.

The exact behavior for scalars, mappings, named context, and chain transfer must be specified before implementation. The language-level goal is that `*` remain visually small and semantically precise.

## `:` is a continuation marker, not a control-flow block

A colon at the end of a recipe line should allow one logical operation to continue across indented physical lines.

```text
charger recover:
    --mode safe
    --timeout 2m
    --retries 3
```

This should be equivalent to a one-line invocation with the same arguments.

The purpose is reviewability: long operations become easier to inspect when each important argument has its own line.

The colon has a deliberately narrow meaning:

> `:` means that the current operation continues structurally on the following indented lines.

Indentation after the colon does not create arbitrary Python-like execution scope. Continuation lines belong to the preceding operation and should initially be limited to syntax that attaches to that operation, such as arguments or modifiers.

## `-->` expresses a desired state

Recipes often care more about the state reached than the low-level repetition used to reach it.

The long-term recipe syntax should use:

```text
operation --> condition
```

The spelling is exactly two dashes followed by the angle bracket: `-->`.

Example:

```text
charger recover --> available
```

This is the recipe-level expression of an `until`-style operation. Conceptually it means:

> Apply the semantic operation `recover` to the current charger, then evaluate the fitness condition represented by `available` against the operation result and semantic context.

The right-hand side should eventually resolve to a semantic fitness function, not merely an arbitrary string.

Examples:

```text
service start --> healthy
wire connect --> reachable
charger recover --> available
deployment apply --> converged
upgrade arthexis --> arthexis good
```

The initial execution model may perform the operation once and evaluate fitness once. Later execution policy may poll, retry, wait on events, select another compatible realization, or fail. The recipe expresses the authorized operation and desired state rather than the mechanics of persistence.

## Continuation and desired-state syntax compose

The two constructs should work together:

```text
upgrade arthexis --> arthexis good:
    --install
    --service
    --role Watchtower
    --site arthexis.com
```

Continuation flags belong to the operation/execution construct on the left-hand side. They are not implicitly routed to the fitness function. A fitness function referenced through `-->` consumes the operation result and semantic context through normal GWAY resolution and adaptation rather than receiving flags from the continued statement.

If a fitness function is invoked directly as an ordinary command, it may expose its own flags for diagnostics or specialized behavior:

```text
arthexis good --details
```

That standalone invocation is distinct from fitness use through `-->`. This keeps recipe meaning stable if a fitness function later gains new optional parameters and avoids introducing a second ambiguous flag-routing mechanism.

Values intentionally shared by the operation and fitness predicate belong in semantic context or a prior store, where each consumer may resolve them independently.

## Desired state is a fitness function

`-->` should eventually correspond to a general desired-state or fitness-function model.

The operation defines the family of actions GWAY is authorized to attempt. The fitness condition defines success. Execution policy defines how aggressively GWAY may pursue that success.

Conceptually:

```text
operation result + semantic context --> fitness -> true | false
```

A fitness function is a semantic predicate. When used through `-->`, its recipe-visible result is satisfied or not satisfied. Rich diagnostics may still be recorded in explain/provenance output or exposed by invoking the fitness function directly as an ordinary command, but those diagnostics do not become the primary recipe result.

The fitness function may naturally consume values produced by the operation. For example, an operation may return a shard ID, token, state ID, or mapping containing several identifiers, and the fitness predicate should receive or resolve those values through the same GWAY transfer, context, and adapter machinery used by ordinary commands.

For example:

```text
create shard --> shard healthy
issue token --> token active
upgrade arthexis --> arthexis good
```

If `create shard` returns the identifier of the new shard, `shard healthy` may consume that identifier directly. If the operation returns a mapping, the predicate may resolve the named values it requires from that result and the accumulated semantic context.

Fitness evaluation must not replace the operation result. The operation result remains the primary result of the complete `operation --> fitness` construction and publishes into recipe context exactly as the operation would have published by itself. Fitness determines whether execution may continue; it does not overwrite `result` or flatten its own diagnostic return values into ordinary context.

Conceptually:

```text
operation
    -> operation_result
    -> publish operation_result to normal context
    -> fitness(operation_result, semantic_context)
        -> true: continue, preserving operation_result
        -> false: semantic failure
```

Safe defaults should be conservative. Operations may declare that retries are unsafe, unsupported, or unnecessary. Targets may also constrain whether an `until`/fitness model is valid.

`-->` should therefore not be universal syntactic sugar. It should only be accepted where the operation and target expose a compatible condition protocol.

## Human review and progressive explanation

Recipes are intended to become the primary human-review surface for operational changes.

A reviewer should be able to approve a short recipe instead of inspecting a large generated script. If a line is unclear, GWAY should support progressive explanation:

```text
intent
-> recipe line
-> semantic operation
-> resolved targets and effects
-> selected adapter/implementation
-> low-level implementation details
```

The short recipe is the human-readable contract. The exact implementation identity, dependency versions, targets, parameters, and execution plan should remain machine-verifiable and auditable.

An approval should eventually bind to the exact recipe revision and resolved execution identity, so implementation changes invalidate stale approvals.

## Operators and authorization

The intended user of this model is an operator: a person trained both in GWAY operational semantics and in a specific field domain.

The AI or conversational layer may propose and explain operations, but authority should be enforced by the underlying system. Semantic operation families can eventually support capability-based authorization such as:

```text
allow Inspect
allow Query
allow Verify
require approval Restart
require approval Configure
deny FactoryReset
```

This allows a Watchtower or other execution boundary to enforce policy independently of the conversational planner.

## Design constraints

The long-term recipe language should preserve these principles:

1. Prefer semantic verbs over low-level mechanics.
2. Keep recipes short enough for human review.
3. Let context remove redundant syntax only when resolution is deterministic.
4. Make desired state explicit with `-->` rather than encoding retry loops in recipes.
5. Use `:` only for continuation/readability, not arbitrary control-flow blocks.
6. Keep complex algorithms in implementation code, not `.rx`.
7. Make every abstraction recursively explainable.
8. Treat semantic names as contracts, not decoration.
9. Preserve provenance from recipe line to every concrete operation executed.
10. Favor conservative, machine-checkable execution and authorization semantics.

## Near-term syntax candidate

The first construct worth implementing is colon continuation, because it improves existing recipe readability without requiring the larger semantic-operation system.

Initial target:

```text
some operation:
    --flag-one value
    --flag-two value
    --flag-three
```

The parser should normalize this into the same logical statement as the current one-line form before ordinary GWAY tokenization/resolution proceeds.

A continued operation is one logical statement for statement indexing, checkpoints, resume validation, errors, and execution events. Its primary source line is the first physical line of the continued operation. Implementations should also preserve the full physical source span so diagnostics and explain output can point back to the continuation lines that supplied individual arguments without treating those lines as separate executable statements.

`-->`, context-derived operations, semantic verb protocols, and `*` result-set application should remain documented goals until their individual semantics are specified and implemented deliberately.
