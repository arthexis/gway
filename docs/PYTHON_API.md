# Python API Contract

GWAY keeps a first-class importable API in addition to the `gway` executable.

The stable import is:

```python
from gway import gway as gw
```

A compatibility alias remains available:

```python
from gway import gw
```

## Current surface

The facade currently shares GWAY's registry and exposes registered-project metadata:

```python
gw.projects()
gw.project("wireguard")
```

Managed command dispatch through dynamic namespaces is **not implemented yet** in the Python facade.

## Required command-dispatch contract

When Python managed-command dispatch is implemented, it should mirror CLI namespaces:

```python
gw.wireguard.status()
gw.arthexis.check()
```

The facade must delegate through the same registry, adapter, dispatcher, and runner used by the CLI. It must not bypass managed project environments by importing every project directly into the caller's interpreter.

The intended invariant is that:

```text
gway wireguard status
```

and:

```python
gw.wireguard.status()
```

resolve to the same managed project and command semantics. New dispatcher behavior should remain available through this shared execution model unless it is inherently CLI-only presentation or parsing behavior.
