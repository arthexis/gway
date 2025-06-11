GWAY
====

Welcome [Viajante], this is the GWAY project README.rst file and website.

**GWAY** is an **experimental** CLI and function-dispatch framework that allows you to invoke and chain Python functions from your own projects or built-ins, with automatic sigil & context resolution, argument injection, inversion control, auto-wired recipes, and multi-environment support. GWAY is async-compatible and fully instrumented.

`Our Goal: Lower the barrier to a higher-level of systems integration.`

`Philosophy: Every function should be a solution and entry point.`

Fetch the source, changelogs and issues (or submit your own) here:

https://github.com/arthexis/gway

Watch the live demo here (if you aren't there already):

https://arthexis.com/gway/readme

Features
--------

- 🔌 Seamless from CLI or code (e.g., ``gw.awg.find_cable()`` is ``gway awg find-cable``)
- ⛓️ CLI chaining: ``proj1 func1 - proj2 func2`` (implicit parameter passing by name)
- 🧠 Sigil-based context resolution (e.g., ``[result-context-environ|fallback]``)
- ⚙️ Automatic CLI generation, with support for ``*``, ``*args`` and ``**kwargs``
- 🧪 Built-in test runner and self-packaging: ``gway test`` and ``gway release build``
- 📦 Environment-aware loading (e.g., ``clients`` and ``servers`` .env files)

Examples
--------

AWG Cable Calculation
~~~~~~~~~~~~~~~~~~~~~

Given ``projects/awg.py`` containing logic to calculate cable sizes and conduit requirements:

**Call from Python**

.. code-block:: python

    from gway import gw

    result = gw.awg.find_cable(meters=30, amps=60, material="cu", volts=240)
    print(result)

**Call from CLI**

.. code-block:: bash

    # Basic cable sizing
    gway awg find-cable --meters 30 --amps 60 --material cu --volts 240

    # With conduit calculation
    gway awg find-cable --meters 30 --amps 60 --material cu --volts 240 --conduit emt

**Chaining Example**

.. code-block:: bash

    # Chain cable calculation and echo the result
    gway awg find-cable --meters 25 --amps 60 - print --text "[awg]"

**Online Example**

You can test the AWG cable sizer online here, or in your own instance:

https://arthexis.com/gway/awg-finder


GWAY Website Server
~~~~~~~~~~~~~~~~~~~

You can also run a bundled lightweight help/documentation server using a GWAY Recipe:

.. code-block:: powershell

    > gway -dr website

This launches an interactive web UI that lets you browse your project, inspect help docs, and search callable functions.


Visit `http://localhost:8888` once it's running.


You can use a similar syntax to lunch any .gwr (GWAY Recipe) files you find. You can register them on your OS for automatic execution with the following command (Administrator/root privileges may be required):


.. code-block:: powershell

    > gway recipe register-gwr


Online Help & Documentation
---------------------------

Browse built-in and project-level function documentation online at:

📘 https://arthexis.com/gway/help

- Use the **search box** in the top left to find any callable by name (e.g., ``find_cable``, ``resource``, ``start_server``).
- You can also navigate directly to: ``https://arthexis.com/gway/help/<project>/<function>`` or ``https://arthexis.com/gway/help/<built-in>``

This is useful for both the included out-of-the-box GWAY tools and your own projects, assuming they follow the GWAY format.


Installation
------------

Install via PyPI:

.. code-block:: bash

    pip install gway

Install from Source:

.. code-block:: bash

    git clone https://github.com/arthexis/gway.git
    cd gway

    # Run directly from shell or command prompt
    ./gway.sh        # On Linux/macOS
    gway.bat         # On Windows

When running GWAY from source for the first time, it will **auto-install** dependencies if needed.

To **upgrade** to the latest version from source:

.. code-block:: bash

    ./upgrade.sh     # On Linux/macOS
    upgrade.bat      # On Windows

This pulls the latest updates from the `main` branch and refreshes dependencies.

Project Structure
-----------------

Here's a quick reference of the main directories in a typical GWAY workspace:

+----------------+-------------------------------------------------------------+
| Directory      | Description                                                 |
+================+=============================================================+
| envs/clients/  | Per-user environment files (e.g., ``username.env``)         |
+----------------+-------------------------------------------------------------+
| envs/servers/  | Per-host environment files (e.g., ``hostname.env``)         |
+----------------+-------------------------------------------------------------+
| projects/      | Your own Python modules — callable via GWAY                 |
+----------------+-------------------------------------------------------------+
| logs/          | Runtime logs and outputs                                    |
+----------------+-------------------------------------------------------------+
| gway/          | Source code for the core GWAY components.                   |
+----------------+-------------------------------------------------------------+
| tests/         | Unit tests for code in gway/ and projects/                  |
+----------------+-------------------------------------------------------------+
| data/          | Static assets, resources, and other data files              |
+----------------+-------------------------------------------------------------+
| temp/          | Temporary working directory for intermediate output files   |
+----------------+-------------------------------------------------------------+
| scripts/       | .gws script files (for --batch mode)                        |
+----------------+-------------------------------------------------------------+


After placing your modules under `projects/`, you can immediately invoke them from the CLI with:

.. code-block:: bash

    gway project-dir-or-script your-function argN --kwargN valueN


By default, results get reused as context for future calls made with the same Gateway thread.  


🧪 Recipes
----------

Gway recipes are lightweight `.gwr` scripts containing one command per line, optionally interspersed with comments. These recipes are executed sequentially, with context and results automatically passed from one step to the next.

Each line undergoes **sigil resolution** using the evolving context before being executed. This makes recipes ideal for scripting interactive workflows where the result of one command feeds into the next.

🔁 How It Works
~~~~~~~~~~~~~~~

Under the hood, recipes are executed using the `run_recipe` function:

.. code-block:: python

    from gway import gw

    # Run a named recipe
    gw.recipe.run("example")
    # This is exactly the same but is a builtin (no difference otherwise)
    gw.run_recipe("example")

    # Or with extra context:
    # Project and size are assumed to be parameters of the example function.
    gw.recipe.run("example", project="Delta", size=12)

If the file isn't found directly, Gway will look in its internal `recipes/` resource folder.


🌐 Example: `website.gwr`
~~~~~~~~~~~~~~~~~~~~~~~~~

An example recipe named `dev-website.gwr` is already included. It generates a basic web setup using inferred context. Default parameters are taken from client and server .envs where possible automatically. It goes beyond the basic help website by providing aditional debugging and browser instrumentiation features. Here's what it contains:

.. code-block:: 

    # Default GWAY website ingredients

    [PENDING]


You can run it with:

.. code-block:: bash

    gway -r dev-website.gwr


Or in Python:

.. code-block:: python

    from gway import gw
    gw.run("dev-website")


This script sets up a web application, launches the server in daemon mode, and waits for lock conditions using built-in context.

---

Recipes make Gway scripting modular and composable. Include them in your automation flows for maximum reuse and clarity.


Design Philosophy
=================

This section contains notes from the author on the nature of the code that may provide insight and guidance to future developers.


On Comments
-----------

Comments and code are like DNA — they reflect each other.

This reflection creates a form of internal consistency and safety.
When code and its comments are in alignment, they mutually verify each other.
When they diverge, the inconsistency acts as a warning sign: something is broken, outdated, or misunderstood.

Treat comments not as annotations, but as the complementary strand of the code itself.
Keep them synchronized.
A mismatch is not a small issue — it's a mutation worth investigating.


The Rule of Three (aka. The Holy Hand Grenade Procedure)
--------------------------------------------------------

If there is *not* only one good way to do it, then you should have **three**.

**Five is right out.**

One way implies clarity. Two implies division. Three implies depth. Five implies confusion, and confusion leads to bugs.

When offering choices — in interface, design, or abstraction — ensure there are no more than three strong forms. The third may be unexpected, but it must still be necessary.

Beyond that, you're just multiplying uncertainty.


INCLUDED PROJECTS
=================

.. rubric:: web.app

- ``build_url`` — (no description)

  > ``gway web app build-url``

- ``redirect_error`` — (no description)

  > ``gway web app redirect-error``

- ``render_navbar`` — (no description)

  > ``gway web app render-navbar``

- ``render_template`` — (no description)

  > ``gway web app render-template``

- ``security_middleware`` — (no description)

  > ``gway web app security-middleware``

- ``setup`` — Configure one or more Bottle-based apps. Use "web server start-app" to launch.

  > ``gway web app setup``

- ``static_file`` — Open a file in a safe way and return an instance of :exc:`HTTPResponse`

  > ``gway web app static-file``

- ``template`` — Get a rendered template as a string iterator.

  > ``gway web app template``

- ``urlencode`` — Encode a dict or sequence of two-element tuples into a URL query string.

  > ``gway web app urlencode``

- ``wraps`` — Decorator factory to apply update_wrapper() to a wrapper function

  > ``gway web app wraps``



License
-------

MIT License
