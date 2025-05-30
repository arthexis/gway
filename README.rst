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


License
-------

MIT License

INCLUDED PROJECTS
=================


============
Project: awg
============

+----------------------+--------------------------------------+
| Function             | Docstring                            |
+======================+======================================+
| find_cable           | Calculate the type of cable needed...  |
|                      | gway awg find_cable                     |
+----------------------+--------------------------------------+
| find_conduit         | Calculate the kind of conduit...       |
|                      | gway awg find_conduit                   |
+----------------------+--------------------------------------+


=============
Project: clip
=============

+----------------------+--------------------------------------+
| Function             | Docstring                            |
+======================+======================================+
| copy                 | Extracts the contents of the...        |
|                      | gway clip copy                           |
+----------------------+--------------------------------------+
| requires             |                                        |
|                      | gway clip requires                       |
+----------------------+--------------------------------------+


==============
Project: etron
==============

+----------------------+--------------------------------------+
| Function             | Docstring                            |
+======================+======================================+
| extract_records      | Load data from EV IOCHARGER to CSV...  |
|                      | gway etron extract_records                |
+----------------------+--------------------------------------+


============
Project: gif
============

+----------------------+--------------------------------------+
| Function             | Docstring                            |
+======================+======================================+
| animate              |                                        |
|                      | gway gif animate                        |
+----------------------+--------------------------------------+


============
Project: gui
============

+----------------------+--------------------------------------+
| Function             | Docstring                            |
+======================+======================================+
| lookup_font          | Look up fonts installed on a...        |
|                      | gway gui lookup_font                    |
+----------------------+--------------------------------------+
| notify               | Show a user interface notification...  |
|                      | gway gui notify                         |
+----------------------+--------------------------------------+
| requires             |                                        |
|                      | gway gui requires                       |
+----------------------+--------------------------------------+


============
Project: job
============

+----------------------+--------------------------------------+
| Function             | Docstring                            |
+======================+======================================+
| schedule             | Schedule a recipe to run.              |
|                      | gway job schedule                       |
+----------------------+--------------------------------------+


============
Project: net
============

+----------------------+--------------------------------------+
| Function             | Docstring                            |
+======================+======================================+
| export_connections   | Export NetworkManager connections...   |
|                      | gway net export_connections             |
+----------------------+--------------------------------------+


=============
Project: ocpp
=============

+----------------------+--------------------------------------+
| Function             | Docstring                            |
+======================+======================================+
| setup_csms_app       | OCPP 1.6 CSMS implementation with:     |
|                      | gway ocpp setup_csms_app                 |
+----------------------+--------------------------------------+
| setup_sink_app       | Basic OCPP passive sink for...         |
|                      | gway ocpp setup_sink_app                 |
+----------------------+--------------------------------------+


=============
Project: odoo
=============

+----------------------+--------------------------------------+
| Function             | Docstring                            |
+======================+======================================+
| Form                 |                                        |
|                      | gway odoo Form                           |
+----------------------+--------------------------------------+
| asynccontextmanager  | @asynccontextmanager decorator.        |
|                      | gway odoo asynccontextmanager            |
+----------------------+--------------------------------------+
| create_quote         | Create a new quotation using a...      |
|                      | gway odoo create_quote                   |
+----------------------+--------------------------------------+
| execute              | A generic function to directly...      |
|                      | gway odoo execute                        |
+----------------------+--------------------------------------+
| fetch_customers      | Fetch customers from Odoo with...      |
|                      | gway odoo fetch_customers                |
+----------------------+--------------------------------------+
| fetch_order          | Fetch the details of a specific...     |
|                      | gway odoo fetch_order                    |
+----------------------+--------------------------------------+
| fetch_products       | Fetch the list of non-archived...      |
|                      | gway odoo fetch_products                 |
+----------------------+--------------------------------------+
| fetch_quotes         | Fetch quotes/quotations from Odoo...   |
|                      | gway odoo fetch_quotes                   |
+----------------------+--------------------------------------+
| fetch_templates      | Fetch available quotation templates... |
|                      | gway odoo fetch_templates                |
+----------------------+--------------------------------------+
| get_user_info        | Retrieve Odoo user information by...   |
|                      | gway odoo get_user_info                  |
+----------------------+--------------------------------------+
| read_chat            | Read chat messages from an Odoo...     |
|                      | gway odoo read_chat                      |
+----------------------+--------------------------------------+
| send_chat            | Send a chat message to an Odoo user... |
|                      | gway odoo send_chat                      |
+----------------------+--------------------------------------+
| setup_chatbot_app    | Create a FastAPI app (or append to...  |
|                      | gway odoo setup_chatbot_app              |
+----------------------+--------------------------------------+


============
Project: png
============

+----------------------+--------------------------------------+
| Function             | Docstring                            |
+======================+======================================+
| credit_images        | Receives a folder containing .png...   |
|                      | gway png credit_images                  |
+----------------------+--------------------------------------+
| sanitize_filename    | Sanitize the credit string to be...    |
|                      | gway png sanitize_filename              |
+----------------------+--------------------------------------+


===========
Project: qr
===========

+----------------------+--------------------------------------+
| Function             | Docstring                            |
+======================+======================================+
| generate_b64data     | Generate a QR code image from the...   |
|                      | gway qr generate_b64data               |
+----------------------+--------------------------------------+
| generate_image       | Generate a QR code image from the...   |
|                      | gway qr generate_image                 |
+----------------------+--------------------------------------+
| generate_img         | Generate a QR code image from the...   |
|                      | gway qr generate_img                   |
+----------------------+--------------------------------------+
| generate_url         | Return the local URL to a QR code...   |
|                      | gway qr generate_url                   |
+----------------------+--------------------------------------+
| requires             |                                        |
|                      | gway qr requires                       |
+----------------------+--------------------------------------+
| scan_image           | Scan the given image (file‑path or...  |
|                      | gway qr scan_image                     |
+----------------------+--------------------------------------+
| scan_img             | Scan the given image (file‑path or...  |
|                      | gway qr scan_img                       |
+----------------------+--------------------------------------+


===============
Project: readme
===============

+----------------------+--------------------------------------+
| Function             | Docstring                            |
+======================+======================================+
| collect_projects     | Update README.rst to include the...    |
|                      | gway readme collect_projects               |
+----------------------+--------------------------------------+
| shorten              | Collapse and truncate the given...     |
|                      | gway readme shorten                        |
+----------------------+--------------------------------------+


===============
Project: recipe
===============

+----------------------+--------------------------------------+
| Function             | Docstring                            |
+======================+======================================+
| register_gwr         | Register the .gwr file extension so... |
|                      | gway recipe register_gwr                   |
+----------------------+--------------------------------------+
| run                  |                                        |
|                      | gway recipe run                            |
+----------------------+--------------------------------------+


================
Project: release
================

+----------------------+--------------------------------------+
| Function             | Docstring                            |
+======================+======================================+
| build                | Build the project and optionally...    |
|                      | gway release build                          |
+----------------------+--------------------------------------+
| build_help           |                                        |
|                      | gway release build_help                     |
+----------------------+--------------------------------------+
| extract_todos        |                                        |
|                      | gway release extract_todos                  |
+----------------------+--------------------------------------+


============
Project: sql
============

+----------------------+--------------------------------------+
| Function             | Docstring                            |
+======================+======================================+
| connect              | Connects to a SQLite database using... |
|                      | gway sql connect                        |
+----------------------+--------------------------------------+
| contextmanager       | @contextmanager decorator.             |
|                      | gway sql contextmanager                 |
+----------------------+--------------------------------------+
| infer_type           | Infer SQL type from a sample value.    |
|                      | gway sql infer_type                     |
+----------------------+--------------------------------------+


==========
Project: t
==========

+----------------------+--------------------------------------+
| Function             | Docstring                            |
+======================+======================================+
| now                  | Return the current datetime object.    |
|                      | gway t now                            |
+----------------------+--------------------------------------+
| now_plus             | Return current datetime plus given...  |
|                      | gway t now_plus                       |
+----------------------+--------------------------------------+
| to_download          | Prompt: Create a python function...    |
|                      | gway t to_download                    |
+----------------------+--------------------------------------+
| ts                   | Return the current timestamp in...     |
|                      | gway t ts                             |
+----------------------+--------------------------------------+


==============
Project: tests
==============

+----------------------+--------------------------------------+
| Function             | Docstring                            |
+======================+======================================+
| dummy_function       | Dummy function for testing.            |
|                      | gway tests dummy_function                 |
+----------------------+--------------------------------------+
| variadic_both        |                                        |
|                      | gway tests variadic_both                  |
+----------------------+--------------------------------------+
| variadic_keyword     |                                        |
|                      | gway tests variadic_keyword               |
+----------------------+--------------------------------------+
| variadic_positional  |                                        |
|                      | gway tests variadic_positional            |
+----------------------+--------------------------------------+


============
Project: web
============

+----------------------+--------------------------------------+
| Function             | Docstring                            |
+======================+======================================+
| awg_finder           | Page builder for AWG cable finder...   |
|                      | gway web awg_finder                     |
+----------------------+--------------------------------------+
| build_url            |                                        |
|                      | gway web build_url                      |
+----------------------+--------------------------------------+
| help                 | Render dynamic help based on GWAY...   |
|                      | gway web help                           |
+----------------------+--------------------------------------+
| qr_code              | Generate a QR code for a given...      |
|                      | gway web qr_code                        |
+----------------------+--------------------------------------+
| readme               | Render the README.rst file as HTML.    |
|                      | gway web readme                         |
+----------------------+--------------------------------------+
| redirect_error       |                                        |
|                      | gway web redirect_error                 |
+----------------------+--------------------------------------+
| requires             |                                        |
|                      | gway web requires                       |
+----------------------+--------------------------------------+
| setup_app            | Configure a simple application that... |
|                      | gway web setup_app                      |
+----------------------+--------------------------------------+
| setup_proxy          | Create a proxy handler to the given... |
|                      | gway web setup_proxy                    |
+----------------------+--------------------------------------+
| start_server         | Start an HTTP (WSGI) or ASGI server... |
|                      | gway web start_server                   |
+----------------------+--------------------------------------+
| theme                | Allows user to choose from...          |
|                      | gway web theme                          |
+----------------------+--------------------------------------+
| urlencode            | Encode a dict or sequence of two-...   |
|                      | gway web urlencode                      |
+----------------------+--------------------------------------+
| wraps                | Decorator factory to apply...          |
|                      | gway web wraps                          |
+----------------------+--------------------------------------+


License
-------

MIT License
