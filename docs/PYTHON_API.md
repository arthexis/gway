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

Managed projects mirror the CLI namespace:

```python
gw.wireguard.status()
gw.arthexis.check()
```

The Python facade delegates through the same registry, adapter, dispatcher, and runner used by the CLI. It must not bypass managed project environments by importing every project directly into the caller's interpreter.

This means the CLI and Python API are two front ends over the same command model:

```text
gway wireguard status
```

and:

```python
gw.wireguard.status()
```

resolve to the same managed project and command semantics. New dispatcher behavior should remain available through this shared execution model unless it is inherently CLI-only presentation or parsing behavior.
