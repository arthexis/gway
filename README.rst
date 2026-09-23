GWAY
====

GWAY is a small Python command-dispatch and composition framework.

It exposes ordinary Python callables as command-line operations, binds CLI
arguments to their signatures, carries named context between operations, and
lets those operations be composed from the CLI, recipes, or Python.

GWAY provides reusable platform and orchestration behavior while applications
keep their own domain logic. A useful boundary is: **GWAY follows the platform;
applications follow the business.**

Quick start
-----------

Install GWAY with Python 3.13 or newer:

.. code-block:: bash

   python3.13 -m pip install gway

Python 3.10 needs the TOML compatibility extra:

.. code-block:: bash

   python3.10 -m pip install "gway[toml]"

Then run an operation:

.. code-block:: bash

   gway env PATH
   gway help copy

Operations can be composed. A standalone dash passes the previous raw result to
the next operation:

.. code-block:: text

   producer - consumer

Named values published by operations remain available as semantic context for
later operations.

Projects
--------

GWAY follows standard Python project metadata.

The nearest ``pyproject.toml`` identifies a project. ``[project].name`` gives
the project identity, and standard ``[project.scripts]`` entries can be exposed
as operations.

GWAY infers project behavior from standard metadata wherever possible.
GWAY-specific configuration should only be added when standard project metadata
cannot express the intent.

Managed installations keep their installation state separately from the source
checkout and disposable cache.

See `docs/PROJECTS.md <https://github.com/arthexis/gway/blob/main/docs/PROJECTS.md>`_
for the complete project-discovery contract and every project-level attribute
GWAY currently reads.

Recipes
-------

Recipes are small ``.rx`` files that compose ordinary GWAY operations:

.. code-block:: bash

   gway ./recipes/deploy.rx --site MTY

Recipes use the same dispatcher and context model as the CLI. They are intended
for readable orchestration rather than as a replacement for Python.

Advanced recipe behavior—including sigils, companion Python files, nested
recipes, checks, repeat, rollback journals, reload/process handoff, and execution boundaries—is
documented in `docs/RECIPES.md <https://github.com/arthexis/gway/blob/main/docs/RECIPES.md>`_.

Logging
-------

GWAY provides one logical logging surface across journald and portable rotating
files:

.. code-block:: bash

   gway log sources
   gway log read arthexis --since "10 minutes ago"
   gway log tail arthexis/web --limit 50
   gway log search "connection refused" arthexis

Journald is used automatically when available. Otherwise GWAY uses structured
rotating files. With no source argument, reads remain limited to GWAY-managed
sources rather than the entire host journal. See
`docs/LOGGING.md <https://github.com/arthexis/gway/blob/main/docs/LOGGING.md>`_
for the source model, backend behavior, and portable query semantics.

Documentation
-------------

- `docs/PROJECTS.md <https://github.com/arthexis/gway/blob/main/docs/PROJECTS.md>`_ — project discovery, standard metadata, GWAY variables, and Sous Chef attributes.
- `docs/RECIPES.md <https://github.com/arthexis/gway/blob/main/docs/RECIPES.md>`_ — complete recipe language and execution semantics.
- `docs/PLATFORM.md <https://github.com/arthexis/gway/blob/main/docs/PLATFORM.md>`_ — GWAY's platform/application ownership boundary.
- `docs/LOGGING.md <https://github.com/arthexis/gway/blob/main/docs/LOGGING.md>`_ — unified logging sources, queries, and backend policy.
- `docs/MCP.md <https://github.com/arthexis/gway/blob/main/docs/MCP.md>`_ — MCP transport, authorization, token/scope, and deployment model.
- `docs/README.md <https://github.com/arthexis/gway/blob/main/docs/README.md>`_ — documentation index.
- `GLOSSARY.md <https://github.com/arthexis/gway/blob/main/GLOSSARY.md>`_ — canonical GWAY terminology.
- `AGENTS.md <https://github.com/arthexis/gway/blob/main/AGENTS.md>`_ — maintainer and automation guidance.

Development
-----------

Install the active checkout with development tools.

With Python 3.13 or newer:

.. code-block:: bash

   python3.13 -m pip install -e ".[dev]"

With Python 3.10, include the TOML compatibility extra:

.. code-block:: bash

   python3.10 -m pip install -e ".[dev,toml]"

Run the test and quality suites:

.. code-block:: bash

   python -m pytest -q
   python -m ruff check gway tests

CI exercises the supported Python versions defined by the repository workflows.

License
-------

MIT License.
