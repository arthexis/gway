# GWAY command chaining

GWAY chains commands with a standalone `-`. The common case is intentionally simple:

```text
gway producer - consumer
```

The result of `producer` becomes leading positional input to `consumer`.

```text
gway producer - consumer tail
```

behaves like passing the producer result before `tail`.

Only a standalone `-` separates stages. Normal flags such as `-i` are not chain separators, and tokens after `--` stay literal within that stage.

## Natural result transfer

GWAY normalizes each completed stage result before the next stage runs:

| Result | Next-stage behavior |
| --- | --- |
| `None` | passes no positional value |
| scalar or string | passes one positional value |
| `bytes` / `bytearray` | passes one scalar value, never individual bytes |
| non-string sequence | spreads values in order |
| mapping | adds keys to chain context and passes no positional values |

Transferred values are data, not fresh CLI syntax. A producer result such as `[cwd]`, `--help`, `--`, or `--unknown` is not intentionally reinterpreted as a Sigil or GWAY option by the chain transport.

## Chain context

Every chain has invocation-local context. After each stage the complete latest result is available as:

```text
[result]
```

If a result is a mapping, its members are also available to later Sigils:

```text
gway device info - % Device [name] is [status]
```

Chain-provided values outrank adapter-provided Sigil context. GWAY's framework-owned roots (`cwd`, `home`, `gway`, `project`, and `command`) remain reserved; a mapping cannot replace those roots. The complete mapping is still available through `[result]`.

Chain context is reset when the chain exits, including when a stage fails.

## Explicit positional routing

The default receiving stage behaves as though all transferred values were inserted at its beginning:

```text
producer - consumer arg
```

Conceptually this is:

```text
producer - consumer [*] arg
```

You only need selectors when you want to rearrange, select, or discard transfer values.

`[N]` selects the Nth transferred positional value, using 1-based indexing:

```text
producer - consumer [2] [1]
```

If the producer returns `A B C D`, the consumer receives `B A`.

`[*]` contributes every transferred value not explicitly selected elsewhere in the receiving stage, preserving original order:

```text
producer - consumer [3] [*] [1]
```

With `A B C D`, the consumer receives:

```text
C B D A
```

The presence of any `[N]` or `[*]` switches that receiving command stage into explicit-transfer mode. The automatic leading transfer is disabled.

Numeric selectors may be repeated intentionally:

```text
producer - consumer [2] [2]
```

Multiple `[*]` selectors in one stage are invalid. An out-of-range `[N]` is an error. A mapping result provides context but no numbered transfer values, so `[1]` after a mapping result is out of range.

Ordinary Sigils are not routing selectors:

```text
producer - consumer [extra]
```

still receives the producer result implicitly before the resolved `[extra]` value.

## Solve/template stages

A stage beginning with `%` is an explicit greedy solve stage:

```text
gway % Hello [name] - uppercase
```

A stage beginning with a bracketed Sigil is an implicit solve stage:

```text
gway [name] is online - uppercase
```

Both consume their full stage up to the next real chain boundary and participate in chaining as ordinary producers or consumers.

`%` is structural only when it is the first token of a stage. Elsewhere it is literal text:

```text
gway % Battery at 50 %
```

An exact single Sigil preserves its resolved native value. Text surrounding Sigils produces interpolated text.

Routing selectors are routing syntax only in normal command stages. Inside solve/template stages, bracket expressions belong to template resolution.

## Escapes

GWAY provides lexical escapes for syntax that would otherwise collide with chaining or Sigils:

```text
[-]       literal standalone -
[[        literal [
]]        literal ]
[[name]]  literal [name]
```

For example:

```text
gway % [name] [-] [status] - uppercase
```

contains one literal dash in the solve text and one real chain boundary.

## Failure behavior

Stages execute from left to right. If stage N fails, later stages do not run. Invocation-local chain and transfer state is restored even on failure.

## Command spelling

Managed command path components accept both dash and underscore spellings. For example, these address the same command:

```text
gway node node-role
gway node node_role
```

The same equivalence applies when a managed command is referenced from a GWAY-backed Sigil.
