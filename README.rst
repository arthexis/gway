GWAY
====

Welcome [Viajante], this is the GWAY project README.rst file and website.

**GWAY** is an **experimental** CLI and function-dispatch framework that allows you to invoke and chain Python functions from your own projects or built-ins, with automatic sigil & context resolution, argument injection, inversion control, auto-wired recipes, and multi-environment support. GWAY is async-compatible and fully instrumented.

`Lowering barrier to enter a higher-level of programming.`


Features
--------

- 🔌 Seamless function calling from CLI or code (e.g., ``gway.awg.find_cable()``)
- ⛓️ CLI chaining support: ``proj 1 func1 - proj2 func2`` (flexible separators)
- 🧠 Sigil-based context resolution (e.g., ``[result_context_or_env_key|fallback]``)
- ⚙️ Automatic CLI argument generation, with support for ``*args`` and ``**kwargs``
- 🧪 Built-in test runner and self-packaging: ``gway test`` and ``gway release build``
- 📦 Environment-aware loading (e.g., ``clients`` and ``servers`` .env files)

Examples
--------

AWG Cable Calculation
~~~~~~~~~~~~~~~~~~~~~

Given a project ``awg.py`` containing logic to calculate cable sizes and conduit requirements:

**Call from Python**

.. code-block:: python

    from gway import gw

    result = gw.awg.find_cable(meters=30, amps=60, material="cu", volts=240)
    print(result)

**Call from CLI**

.. code-block:: bash

    # Basic cable sizing
    gway awg find cable --meters 30 --amps 60 --material cu --volts 240

    # With conduit calculation
    gway awg find cable --meters 30 --amps 60 --material cu --volts 240 --conduit emt

**Chaining Example**

.. code-block:: bash

    # Chain cable calculation and echo the result
    gway awg find cable --meters 25 --amps 60 - print --text "[awg]"

**Online Example**

You can test the AWG cable sizer online here, or in your own instance:

https://arthexis.com/gway/awg-finder


GWAY Website Server
~~~~~~~~~~~~~~~~~~~

You can also run a lightweight help/documentation server directly using GWAY:

.. code-block:: powershell

    > gway -d web server start --daemon - until --lock-pypi

This launches an interactive web UI that lets you browse your project, inspect help docs, and search callable functions.

Visit `http://localhost:8888` once it's running.

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
| tests/         | Unit tests for your own projects                            |
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

    # Or with extra context:
    # Project and size are assumed to be parameters of the example function.
    gw.recipe.run("example", project="Delta", size=12)

If the file isn't found directly, Gway will look in its internal `recipes/` resource folder.


🌐 Example: `website.gwr`
~~~~~~~~~~~~~~~~~~~~~~~~~

An example recipe named `website.gwr` is already included. It generates a basic web setup using inferred context. Default parameters are taken from client and server .envs where possible automatically. Here's what it contains:

.. code-block:: 

    # Default GWAY website ingredients

    web app setup
    web server start --daemon
    until --lock-file VERSION --lock-pypi


You can run it with:

.. code-block:: bash

    gway -r website


Or in Python:

.. code-block:: python

    from gway import gw
    gw.run("website")


This script sets up a web application, launches the server in daemon mode, and waits for lock conditions using built-in context.

---

Recipes make Gway scripting modular and composable. Include them in your automation flows for maximum reuse and clarity.


INCLUDED PROJECTS
=================

.. rubric:: awg

- ``find_cable`` — Calculate the type of cable needed for an electrical system.

  Example CLI: ``gway awg find cable``

- ``find_conduit`` — Calculate the kind of conduit required for a set of cables.

  Example CLI: ``gway awg find conduit``


.. rubric:: cdv

- ``find`` — (no description)

  Example CLI: ``gway cdv find``


.. rubric:: clip

- ``copy`` — Extracts the contents of the clipboard and returns it.

  Example CLI: ``gway clip copy``


.. rubric:: gif

- ``animate`` — (no description)

  Example CLI: ``gway gif animate``


.. rubric:: job

- ``schedule`` — Schedule a recipe to run.

  Example CLI: ``gway job schedule``


.. rubric:: mail

- ``send`` — Send an email with the specified subject and message, using defaults from env if available.

  Example CLI: ``gway mail send``


.. rubric:: net

- ``export_connections`` — Export NetworkManager connections into a JSON-serializable list of dicts.

  Example CLI: ``gway net export connections``


.. rubric:: node

- ``register`` — Registers this node with the given server's registration endpoint.

  Example CLI: ``gway node register``


.. rubric:: ocpp

- ``setup_csms_app`` — OCPP 1.6 CSMS implementation with:

  Example CLI: ``gway ocpp setup csms app``

- ``setup_sink_app`` — Basic OCPP passive sink for messages, acting as a dummy CSMS server.

  Example CLI: ``gway ocpp setup sink app``


.. rubric:: odoo

- ``Form`` — (no description)

  Example CLI: ``gway odoo Form``

- ``asynccontextmanager`` — @asynccontextmanager decorator.

  Example CLI: ``gway odoo asynccontextmanager``

- ``create_quote`` — Create a new quotation using a specified template and customer name.

  Example CLI: ``gway odoo create quote``

- ``execute`` — A generic function to directly interface with Odoo's execute_kw method.

  Example CLI: ``gway odoo execute``

- ``fetch_customers`` — Fetch customers from Odoo with optional filters.

  Example CLI: ``gway odoo fetch customers``

- ``fetch_order`` — Fetch the details of a specific order by its ID from Odoo, including all line details.

  Example CLI: ``gway odoo fetch order``

- ``fetch_products`` — Fetch the list of non-archived products from Odoo.

  Example CLI: ``gway odoo fetch products``

- ``fetch_quotes`` — Fetch quotes/quotations from Odoo with optional filters.

  Example CLI: ``gway odoo fetch quotes``

- ``fetch_templates`` — Fetch available quotation templates from Odoo with optional filters.

  Example CLI: ``gway odoo fetch templates``

- ``get_user_info`` — Retrieve Odoo user information by username.

  Example CLI: ``gway odoo get user info``

- ``read_chat`` — Read chat messages from an Odoo user by username.

  Example CLI: ``gway odoo read chat``

- ``send_chat`` — Send a chat message to an Odoo user by username.

  Example CLI: ``gway odoo send chat``

- ``setup_chatbot_app`` — Create a FastAPI app (or append to existing ones) serving a chatbot UI and logic.

  Example CLI: ``gway odoo setup chatbot app``


.. rubric:: png

- ``credit_images`` — Receives a folder containing .png image files and uses a reverse image lookup

  Example CLI: ``gway png credit images``

- ``sanitize_filename`` — Sanitize the credit string to be filesystem-safe.

  Example CLI: ``gway png sanitize filename``


.. rubric:: qr

- ``generate_b64data`` — Generate a QR code image from the given value and return it as a base64-encoded PNG string.

  Example CLI: ``gway qr generate b64data``

- ``generate_image`` — Generate a QR code image from the given value and save it to the specified path.

  Example CLI: ``gway qr generate image``

- ``generate_img`` — Generate a QR code image from the given value and save it to the specified path.

  Example CLI: ``gway qr generate img``

- ``generate_url`` — Return the local URL to a QR code with the given value. 

  Example CLI: ``gway qr generate url``

- ``requires`` — (no description)

  Example CLI: ``gway qr requires``

- ``scan_image`` — Scan the given image (file‑path or PIL.Image) for QR codes and return

  Example CLI: ``gway qr scan image``

- ``scan_img`` — Scan the given image (file‑path or PIL.Image) for QR codes and return

  Example CLI: ``gway qr scan img``


.. rubric:: readme

- ``collect_projects`` — Scan `project_dir` for all modules/packages, collect public functions,

  Example CLI: ``gway readme collect projects``


.. rubric:: recipe

- ``register_gwr`` — Register the .gwr file extension so that double-click launches:

  Example CLI: ``gway recipe register gwr``

- ``run`` — (no description)

  Example CLI: ``gway recipe run``


.. rubric:: release

- ``build`` — Build the project and optionally upload to PyPI.

  Example CLI: ``gway release build``

- ``build_help`` — (no description)

  Example CLI: ``gway release build help``

- ``extract_todos`` — (no description)

  Example CLI: ``gway release extract todos``


.. rubric:: service


.. rubric:: sql

- ``connect`` — Connects to a SQLite database using a context manager.

  Example CLI: ``gway sql connect``

- ``contextmanager`` — @contextmanager decorator.

  Example CLI: ``gway sql contextmanager``

- ``infer_type`` — Infer SQL type from a sample value.

  Example CLI: ``gway sql infer type``


.. rubric:: t

- ``minus`` — Return current datetime plus given seconds.

  Example CLI: ``gway t minus``

- ``now`` — Return the current datetime object.

  Example CLI: ``gway t now``

- ``plus`` — Return current datetime plus given seconds.

  Example CLI: ``gway t plus``

- ``to_download`` — Prompt: Create a python function that takes a file size such as 100 MB or 1.76 GB 

  Example CLI: ``gway t to download``

- ``ts`` — Return the current timestamp in ISO-8601 format.

  Example CLI: ``gway t ts``


.. rubric:: tests

- ``dummy_function`` — Dummy function for testing.

  Example CLI: ``gway tests dummy function``

- ``variadic_both`` — (no description)

  Example CLI: ``gway tests variadic both``

- ``variadic_keyword`` — (no description)

  Example CLI: ``gway tests variadic keyword``

- ``variadic_positional`` — (no description)

  Example CLI: ``gway tests variadic positional``



License
-------

MIT License
