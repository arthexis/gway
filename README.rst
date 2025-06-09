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

.. rubric:: awg

- ``find_cable`` — Calculate the type of cable needed for an electrical system.

  > ``gway awg find-cable``

- ``find_conduit`` — Calculate the kind of conduit required for a set of cables.

  > ``gway awg find-conduit``


.. rubric:: clip

- ``copy`` — Extracts or updates the clipboard contents.

  > ``gway clip copy``


.. rubric:: clock

- ``minus`` — Return current datetime plus given seconds.

  > ``gway clock minus``

- ``now`` — Return the current datetime object.

  > ``gway clock now``

- ``plus`` — Return current datetime plus given seconds.

  > ``gway clock plus``

- ``to_download`` — Prompt: Create a python function that takes a file size such as 100 MB or 1.76 GB 

  > ``gway clock to-download``

- ``ts`` — Return the current timestamp in ISO-8601 format.

  > ``gway clock ts``


.. rubric:: deck

- ``count`` — (no description)

  > ``gway deck count``

- ``deal`` — (no description)

  > ``gway deck deal``

- ``draw`` — (no description)

  > ``gway deck draw``

- ``mark`` — (no description)

  > ``gway deck mark``

- ``shuffle`` — (no description)

  > ``gway deck shuffle``


.. rubric:: etron

- ``extract_records`` — Load data from EV IOCHARGER to CSV format.

  > ``gway etron extract-records``


.. rubric:: mail

- ``message_from_bytes`` — Parse a bytes string into a Message object model.

  > ``gway mail message-from-bytes``

- ``search`` — Search emails by subject and optionally body. Use "*" to match any subject.

  > ``gway mail search``

- ``send`` — Send an email with the specified subject and body, using defaults from env if available.

  > ``gway mail send``


.. rubric:: ocpp

- ``setup_csms_app`` — OCPP 1.6 CSMS implementation with RFID authorization.

  > ``gway ocpp setup-csms-app``

- ``setup_sink_app`` — Basic OCPP passive sink for messages, acting as a dummy CSMS server.

  > ``gway ocpp setup-sink-app``

- ``view_status`` — (no description)

  > ``gway ocpp view-status``


.. rubric:: odoo

- ``Form`` — (no description)

  > ``gway odoo Form``

- ``asynccontextmanager`` — @asynccontextmanager decorator.

  > ``gway odoo asynccontextmanager``

- ``create_quote`` — Create a new quotation using a specified template and customer name.

  > ``gway odoo create-quote``

- ``execute_kw`` — A generic function to directly interface with Odoo's execute_kw method.

  > ``gway odoo execute-kw``

- ``fetch_customers`` — Fetch customers from Odoo with optional filters.

  > ``gway odoo fetch-customers``

- ``fetch_order`` — Fetch the details of a specific order by its ID from Odoo, including all line details.

  > ``gway odoo fetch-order``

- ``fetch_products`` — Fetch the list of non-archived products from Odoo.

  > ``gway odoo fetch-products``

- ``fetch_quotes`` — Fetch quotes/quotations from Odoo with optional filters.

  > ``gway odoo fetch-quotes``

- ``fetch_templates`` — Fetch available quotation templates from Odoo with optional filters.

  > ``gway odoo fetch-templates``

- ``get_user_info`` — Retrieve Odoo user information by username.

  > ``gway odoo get-user-info``

- ``read_chat`` — Read chat messages from an Odoo user by username.

  > ``gway odoo read-chat``

- ``send_chat`` — Send a chat message to an Odoo user by username.

  > ``gway odoo send-chat``

- ``setup_chatbot_app`` — Create a FastAPI app (or append to existing ones) serving a chatbot UI and logic.

  > ``gway odoo setup-chatbot-app``


.. rubric:: qr

- ``generate_b64data`` — Generate a QR code image from the given value and return it as a base64-encoded PNG string.

  > ``gway qr generate-b64data``

- ``generate_image`` — Generate a QR code image from the given value and save it to the specified path.

  > ``gway qr generate-image``

- ``generate_url`` — Return the local URL to a QR code with the given value. 

  > ``gway qr generate-url``

- ``scan_img`` — Scan the given image (file‑path or PIL.Image) for QR codes and return

  > ``gway qr scan-img``


.. rubric:: readme

- ``collect_projects`` — Scan `project_dir` for all modules/packages, collect public functions,

  > ``gway readme collect-projects``


.. rubric:: recipe

- ``register_gwr`` — Register the .gwr file extension so that double-click launches:

  > ``gway recipe register-gwr``

- ``run`` — (no description)

  > ``gway recipe run``


.. rubric:: release

- ``build`` — Build the project and optionally upload to PyPI.

  > ``gway release build``

- ``build_help_db`` — (no description)

  > ``gway release build-help-db``

- ``create_shortcut`` — (no description)

  > ``gway release create-shortcut``

- ``loc`` — Counts Python lines of code in the given directories, ignoring hidden files and directories.

  > ``gway release loc``


.. rubric:: screen

- ``animate_gif`` — (no description)

  > ``gway screen animate-gif``

- ``lookup_font`` — Look up fonts installed on a Windows system by partial name (prefix).

  > ``gway screen lookup-font``

- ``notify`` — Show a user interface notification with the specified title and message.

  > ``gway screen notify``

- ``reminder`` — (no description)

  > ``gway screen reminder``

- ``shot`` — Take a screenshot in the specified mode and save it under:

  > ``gway screen shot``


.. rubric:: sql

- ``close_connection`` — Explicitly close one or all cached database connections.

  > ``gway sql close-connection``

- ``execute`` — Execute SQL code or a script resource. If both are given, run script first.

  > ``gway sql execute``

- ``infer_type`` — (no description)

  > ``gway sql infer-type``

- ``load_csv`` — Recursively loads CSVs from a folder into SQLite tables.

  > ``gway sql load-csv``

- ``open_connection`` — Initialize or reuse a database connection.

  > ``gway sql open-connection``


.. rubric:: tests

- ``dummy_function`` — Dummy function for testing.

  > ``gway tests dummy-function``

- ``variadic_both`` — (no description)

  > ``gway tests variadic-both``

- ``variadic_keyword`` — (no description)

  > ``gway tests variadic-keyword``

- ``variadic_positional`` — (no description)

  > ``gway tests variadic-positional``

- ``view_index`` — (no description)

  > ``gway tests view-index``


.. rubric:: trigger



License
-------

MIT License
