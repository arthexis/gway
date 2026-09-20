GWAY
====

GWAY is a small Python command-dispatch and composition core.

This branch intentionally contains only the framework core. Bundled projects,
framework integrations, deployment helpers, and optional ingestors have been
removed so the Gateway can be rebuilt from a minimal baseline.

Project conventions
-------------------

GWAY uses standard Python project structure as its primary configuration.
Managed projects require ``pyproject.toml`` and use ``[project].name`` for
identity and ``[project.scripts]`` for explicit console entrypoints. Python
packages with a callable ``__main__`` or conventional ``__main__.py`` are
discovered as executable GWAY operations.

There is no separate ``gway.toml`` project manifest. GWAY-specific TOML is
reserved for policy that cannot be inferred from Python or packaging metadata
and lives under ``[tool.gway]`` in ``pyproject.toml``. For example, semantic
variables use ``[tool.gway.variables]`` and Sous Chef schedules use
``[tool.gway.sous-chef.<job>]``.

Services do not require declarations. Any resolvable GWAY operation or recipe
can be installed or run under service supervision.

Development
-----------

Create an environment, install the package in editable mode, and run the smoke
tests:

.. code-block:: bash

   python -m venv .venv
   python -m pip install -e .
   python -m pip install pytest
   python -m pytest -q

The package currently has no runtime dependencies.

Manual chains
-------------

Python code can mirror recipe-style chaining with a scoped callable chain:

.. code-block:: python

   with gw.chain("chargers") as __:
       __("filter active")
       report = __("summarize")

The name ``__`` is only a convention for short-lived chain variables. Any
valid Python name can be used. Each call receives the previous raw result as
its pipeline input while preserving normal Python return values.

License
-------

MIT License.
