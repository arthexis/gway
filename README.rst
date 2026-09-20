GWAY
====

GWAY is a small Python command-dispatch and composition core. It exposes Python
callables as semantic operations, binds CLI/recipe input to their signatures,
completes missing named values from runtime context, invokes the callable, and
publishes results for later operations.

The framework is intentionally compact. Domain algorithms belong in Python;
GWAY provides the composition, context, recipe, service, installation, and
transaction boundaries around them.

Quick start
-----------

Install the active checkout in editable mode:

.. code-block:: bash

   python -m pip install -e ".[dev,toml]"

Then invoke operations through the CLI:

.. code-block:: bash

   gway env PATH
   gway help copy
   gway ./recipes/deploy.rx --site MTY

The package has no mandatory third-party runtime dependencies. The toml extra
supplies TOML support on Python 3.10, and dev installs the test and quality
tools used by CI.

Composition model
-----------------

A standalone dash transfers the previous raw result to the next stage:

.. code-block:: text

   producer - consumer

Recipe newlines and semicolons start a new statement without raw positional
transfer, while published named semantic context remains available.

Mapping results publish their members into semantic context. Semantic mapping
keys are matched case-insensitively and treat spaces, dashes, and underscores
as equivalent. Ambiguous semantic aliases are rejected rather than selected
arbitrarily.

Recipes
-------

Recipes are .rx files made from ordinary GWAY operations and control stages.
They use the same dispatcher and runtime semantics as the CLI and Python API.

A same-stem Python companion can provide the implementation vocabulary used by
the recipe:

.. code-block:: text

   recipes/
       deploy.rx
       deploy.py

Recipes support nested composition, named context, raw dash pipelines,
physical -- continuation lines, atomic check validation, guarded
check --unless, semantic repeat, and named rollback journals.

A transactional deployment can remain short and reviewable:

.. code-block:: text

   render app.conf.tmpl --to /etc/app.conf --rollback deploy
   service reload app

   service status app
   check --unless [service_disabled] --active --status running --rollback deploy

   commit deploy

For convergent operations:

.. code-block:: text

   probe health
   repeat --until healthy --max 20 --interval 1 --rollback deploy
   commit deploy

See docs/RECIPES.md for the complete current recipe language, companion scripts,
semantic context, check/repeat behavior, rollback lifecycle, failure precedence,
and execution-boundary rules.

Rollback safety
---------------

Rollback-aware filesystem operations currently include copy, move, link,
remove, and render.

A journal records the pre-mutation state and seals the expected post-mutation
state before an entry becomes fully applied. GWAY verifies that post-state
before restoring so it does not blindly overwrite unexpected external changes.

Open journals cannot silently escape the outer execution boundary. A successful
invocation that forgot to commit is automatically rolled back and fails with an
UncommittedJournalError. When execution is already failing, recovery is
attempted while preserving the original failure as primary.

Project conventions
-------------------

GWAY uses standard Python packaging metadata as the primary project contract.
The nearest pyproject.toml is discovered from the current directory upward.

[project].name identifies the local project. [project.scripts] exposes explicit
console entrypoints, and conventional Python packages with executable
__main__ surfaces can be discovered as GWAY operations.

GWAY-specific semantic variables live under:

.. code-block:: toml

   [tool.gway.variables]
   site = "MTY"
   role = "Watchtower"

Managed installations persist their own authoritative installation state
separately from the disposable cache.

Manual chains
-------------

Python code can mirror recipe-style chaining with a scoped callable chain:

.. code-block:: python

   with gw.chain("chargers") as __:
       __("filter active")
       report = __("summarize")

The name __ is only a convention. Each call receives the previous raw result
as its pipeline input while preserving normal Python return values.

Development
-----------

Run quality checks and the full suite from the repository root:

.. code-block:: bash

   .ci/quality.sh --check
   python -m pytest -q

CI currently exercises Python 3.10 and Python 3.13.

Agents and automated contributors should also read AGENTS.md. That file is an
operating guide for the current branch and should describe implemented
behavior, not roadmap syntax.

License
-------

MIT License.
