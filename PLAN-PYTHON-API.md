# Python API requirement

This requirement supplements `PLAN.md` and should be folded into the next plan revision.

GWAY 1.x must remain importable by other Python projects through the stable public facade:

```python
from gway import gway as gw
```

Managed command access should mirror CLI namespaces, for example:

```python
gw.wireguard.status()
gw.arthexis.check()
```

The Python facade and CLI must share the same project registry, adapter selection, dispatcher, and runner. The facade must not bypass managed project isolation by importing every project into the host interpreter.

Required implementation implications:

- Chunk 1 should expose project lookup through reusable Python APIs, not CLI-only functions.
- Chunk 2 should make the dispatcher callable directly from Python.
- Chunk 3 should connect dynamic attribute namespaces to the dispatcher so Python-adapter commands can be invoked as `gw.<project>.<namespace>.<command>(...)`.
- Chunk 6 should expose Django management commands through the same facade, e.g. `gw.arthexis.migrate(...)`.
- CLI argument parsing should be only one frontend; command execution semantics belong below it.
- Return values from managed calls should remain programmatically usable where the runner boundary permits it.

Compatibility alias:

```python
from gway import gw
```

may remain supported as well.
