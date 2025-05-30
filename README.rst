GWAY
====

Welcome [Viajante], this is the GWAY project README.rst file and website.

**GWAY** is an **experimental** CLI and function-dispatch framework that allows you to invoke and chain Python functions from your own projects or built-ins, with automatic sigil & context resolution, argument injection, inversion control, auto-wired recipes, and multi-environment support. GWAY is async-compatible and fully instrumented.

`Lowering barrier to enter a higher-level of programming.`


Features
--------

- 🔌 Seamless function calling from CLI or code (e.g., ``gway.awg.find_cable()``)
- ⛓️ CLI chaining support: ``func1 - func2`` or ``func1 ; func2``
- 🧠 Sigil-based context resolution (e.g., ``[result_context_or_env_key|fallback]``)
- ⚙️ Automatic CLI argument generation, with support for ``*args`` and ``**kwargs``
- 🧪 Built-in test runner and packaging: ``gway run-tests`` and ``gway project build``
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

You can also run a lightweight help/documentation server directly using GWAY:

.. code-block:: powershell

    > gway --debug website start-server --daemon - hold

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

    gway project-name my-function --arg1 value


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

An example recipe named `website.gwr` is already included. It generates a basic web setup using inferred context. Here's what it contains:

.. code-block:: 

    # Default GWAY website ingredients

    web setup-app
    web start-server --daemon
    until --lock-file VERSION --lock-pypi


You can run it with:

.. code-block:: bash

    gway -r website


Or in Python:

.. code-block:: python

    from gway import gw
    gw.recipe.run("website")


This script sets up a web application, launches the server in daemon mode, and waits for lock conditions using built-in context.

---

Recipes make Gway scripting modular and composable. Include them in your automation flows for maximum reuse and clarity.


INCLUDED PROJECTS
=================

.. rubric:: awg

- ``find_cable`` — Calculate the type of cable needed for an electrical system.

  Example CLI: ``gway awg find_cable``

- ``find_conduit`` — Calculate the kind of conduit required for a set of cables.

  Example CLI: ``gway awg find_conduit``


.. rubric:: clip

- ``copy`` — Extracts the contents of the clipboard and returns it.

  Example CLI: ``gway clip copy``

- ``requires`` — (no description)

  Example CLI: ``gway clip requires``


.. rubric:: etron

- ``extract_records`` — Load data from EV IOCHARGER to CSV format.

  Example CLI: ``gway etron extract_records``


.. rubric:: gif

- ``animate`` — (no description)

  Example CLI: ``gway gif animate``


.. rubric:: gui

- ``lookup_font`` — Look up fonts installed on a Windows system by partial name (prefix).

  Example CLI: ``gway gui lookup_font``

- ``notify`` — Show a user interface notification with the specified title and message.

  Example CLI: ``gway gui notify``

- ``requires`` — (no description)

  Example CLI: ``gway gui requires``


.. rubric:: job

- ``schedule`` — Schedule a recipe to run.

  Example CLI: ``gway job schedule``


.. rubric:: net

- ``export_connections`` — Export NetworkManager connections into a JSON-serializable list of dicts.

  Example CLI: ``gway net export_connections``


.. rubric:: ocpp

- ``setup_csms_app`` — OCPP 1.6 CSMS implementation with:

  Example CLI: ``gway ocpp setup_csms_app``

- ``setup_sink_app`` — Basic OCPP passive sink for messages, acting as a dummy CSMS server.

  Example CLI: ``gway ocpp setup_sink_app``


.. rubric:: odoo

- ``Form`` — (no description)

  Example CLI: ``gway odoo Form``

- ``asynccontextmanager`` — @asynccontextmanager decorator.

  Example CLI: ``gway odoo asynccontextmanager``

- ``create_quote`` — Create a new quotation using a specified template and customer name.

  Example CLI: ``gway odoo create_quote``

- ``execute`` — A generic function to directly interface with Odoo's execute_kw method.

  Example CLI: ``gway odoo execute``

- ``fetch_customers`` — Fetch customers from Odoo with optional filters.

  Example CLI: ``gway odoo fetch_customers``

- ``fetch_order`` — Fetch the details of a specific order by its ID from Odoo, including all line details.

  Example CLI: ``gway odoo fetch_order``

- ``fetch_products`` — Fetch the list of non-archived products from Odoo.

  Example CLI: ``gway odoo fetch_products``

- ``fetch_quotes`` — Fetch quotes/quotations from Odoo with optional filters.

  Example CLI: ``gway odoo fetch_quotes``

- ``fetch_templates`` — Fetch available quotation templates from Odoo with optional filters.

  Example CLI: ``gway odoo fetch_templates``

- ``get_user_info`` — Retrieve Odoo user information by username.

  Example CLI: ``gway odoo get_user_info``

- ``read_chat`` — Read chat messages from an Odoo user by username.

  Example CLI: ``gway odoo read_chat``

- ``send_chat`` — Send a chat message to an Odoo user by username.

  Example CLI: ``gway odoo send_chat``

- ``setup_chatbot_app`` — Create a FastAPI app (or append to existing ones) serving a chatbot UI and logic.

  Example CLI: ``gway odoo setup_chatbot_app``


.. rubric:: png

- ``credit_images`` — Receives a folder containing .png image files and uses a reverse image lookup

  Example CLI: ``gway png credit_images``

- ``sanitize_filename`` — Sanitize the credit string to be filesystem-safe.

  Example CLI: ``gway png sanitize_filename``


.. rubric:: qr

- ``generate_b64data`` — Generate a QR code image from the given value and return it as a base64-encoded PNG string.

  Example CLI: ``gway qr generate_b64data``

- ``generate_image`` — Generate a QR code image from the given value and save it to the specified path.

  Example CLI: ``gway qr generate_image``

- ``generate_img`` — Generate a QR code image from the given value and save it to the specified path.

  Example CLI: ``gway qr generate_img``

- ``generate_url`` — Return the local URL to a QR code with the given value. 

  Example CLI: ``gway qr generate_url``

- ``requires`` — (no description)

  Example CLI: ``gway qr requires``

- ``scan_image`` — Scan the given image (file‑path or PIL.Image) for QR codes and return

  Example CLI: ``gway qr scan_image``

- ``scan_img`` — Scan the given image (file‑path or PIL.Image) for QR codes and return

  Example CLI: ``gway qr scan_img``


.. rubric:: readme

- ``collect_projects`` — Scan `project_dir` for all modules/packages, collect public functions,

  Example CLI: ``gway readme collect_projects``


.. rubric:: recipe

- ``register_gwr`` — Register the .gwr file extension so that double-click launches:

  Example CLI: ``gway recipe register_gwr``

- ``run`` — (no description)

  Example CLI: ``gway recipe run``


.. rubric:: release

- ``build`` — Build the project and optionally upload to PyPI.

  Example CLI: ``gway release build``

- ``build_help`` — (no description)

  Example CLI: ``gway release build_help``

- ``extract_todos`` — (no description)

  Example CLI: ``gway release extract_todos``


.. rubric:: sql

- ``connect`` — Connects to a SQLite database using a context manager.

  Example CLI: ``gway sql connect``

- ``contextmanager`` — @contextmanager decorator.

  Example CLI: ``gway sql contextmanager``

- ``infer_type`` — Infer SQL type from a sample value.

  Example CLI: ``gway sql infer_type``


.. rubric:: t

- ``now`` — Return the current datetime object.

  Example CLI: ``gway t now``

- ``now_plus`` — Return current datetime plus given seconds.

  Example CLI: ``gway t now_plus``

- ``to_download`` — Prompt: Create a python function that takes a file size such as 100 MB or 1.76 GB 

  Example CLI: ``gway t to_download``

- ``ts`` — Return the current timestamp in ISO-8601 format.

  Example CLI: ``gway t ts``


.. rubric:: tests

- ``dummy_function`` — Dummy function for testing.

  Example CLI: ``gway tests dummy_function``

- ``variadic_both`` — (no description)

  Example CLI: ``gway tests variadic_both``

- ``variadic_keyword`` — (no description)

  Example CLI: ``gway tests variadic_keyword``

- ``variadic_positional`` — (no description)

  Example CLI: ``gway tests variadic_positional``


.. rubric:: web

- ``awg_finder`` — Page builder for AWG cable finder with HTML form and result.

  Example CLI: ``gway web awg_finder``

- ``build_url`` — (no description)

  Example CLI: ``gway web build_url``

- ``help`` — Render dynamic help based on GWAY introspection and search-style links.

  Example CLI: ``gway web help``

- ``qr_code`` — Generate a QR code for a given value and serve it from cache if available.

  Example CLI: ``gway web qr_code``

- ``readme`` — Render the README.rst file as HTML.

  Example CLI: ``gway web readme``

- ``redirect_error`` — (no description)

  Example CLI: ``gway web redirect_error``

- ``requires`` — (no description)

  Example CLI: ``gway web requires``

- ``setup_app`` — Configure a simple application that showcases the use of GWAY to generate web apps.

  Example CLI: ``gway web setup_app``

- ``setup_proxy`` — Create a proxy handler to the given Bottle app.

  Example CLI: ``gway web setup_proxy``

- ``start_server`` — Start an HTTP (WSGI) or ASGI server to host the given application.

  Example CLI: ``gway web start_server``

- ``theme`` — Allows user to choose from available stylesheets and shows current selection.

  Example CLI: ``gway web theme``

- ``urlencode`` — Encode a dict or sequence of two-element tuples into a URL query string.

  Example CLI: ``gway web urlencode``

- ``wraps`` — Decorator factory to apply update_wrapper() to a wrapper function

  Example CLI: ``gway web wraps``



License
-------

MIT License
