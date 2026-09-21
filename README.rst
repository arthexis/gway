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

Install GWAY:

.. code-block:: bash

   python -m pip install gway

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

Recipes
-------

Recipes are small ``.rx`` files that compose ordinary GWAY operations:

.. code-block:: bash

   gway ./recipes/deploy.rx --site MTY

Recipes use the same dispatcher and context model as the CLI. They are intended
for readable orchestration rather than as a replacement for Python.

Advanced recipe behavior—including sigils, companion Python files, nested
recipes, checks, repeat, rollback journals, reload/process handoff, and execution boundaries—is
documented in ``docs/RECIPES.md``.

Documentation
-------------

- ``docs/RECIPES.md`` — complete recipe language and execution semantics.
- ``docs/PLATFORM.md`` — GWAY's platform/application ownership boundary.
- ``docs/README.md`` — documentation index.
- ``AGENTS.md`` — maintainer and automation guidance.

Development
-----------

Install the active checkout with development tools:

.. code-block:: bash

   python -m pip install -e ".[dev,toml]"

Run the test and quality suites:

.. code-block:: bash

   python -m pytest -q
   python -m ruff check gway tests

CI exercises the supported Python versions defined by the repository workflows.

License
-------

MIT License.
