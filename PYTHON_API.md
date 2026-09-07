# Python API Contract

GWAY 1.x keeps a first-class importable API in addition to the `gway` executable.

The stable import is:

```python
from gway import gway as gw
```

A compatibility alias remains available:

```python
from gway import gw
```

Managed projects should mirror the CLI namespace:

```python
gw.wireguard.status()
gw.arthexis.check()
```

The Python facade must delegate through the same registry, adapter, dispatcher, and runner used by the CLI. It must not bypass managed project environments by importing every project directly into the caller's interpreter.

This means the CLI and Python API are two front ends over the same command model:

```text
gway wireguard status
```

and:

```python
gw.wireguard.status()
```

resolve to the same managed project and command semantics.

The concrete dispatch implementation belongs in the registry/adapter/dispatcher chunks of `PLAN.md`; this file records the public API contract so later work treats it as a required feature rather than an optional legacy compatibility layer.
