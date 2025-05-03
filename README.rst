GWAY
====

Welcome Traveler, this is the GWAY project README.rst file and website.

**GWAY** is a dynamic CLI and function-dispatch framework that allows you to invoke and chain Python functions from your own projects or built-ins, with automatic context resolution, argument injection, and environment support.

Higher-level programming, lower barrier to entry.

Features
--------

- 🔌 Seamless function calling from CLI or code (e.g., ``gway.awg.find_cable()``)
- ⛓️ CLI chaining support: ``func1 - func2`` or ``func1 ; func2``
- 🧠 Sigil-based context resolution (e.g., ``[result_key]``)
- ⚙️ Automatic CLI argument generation, with support for ``*args`` and ``**kwargs``
- 🧪 Built-in test runner: ``gway test``
- 📦 Environment-aware loading (e.g., ``clients``, ``servers``)

Examples
--------

AWG Cable Calculation
~~~~~~~~~~~~~~~~~~~~~

Given a project ``awg.py`` containing logic to calculate cable sizes and conduit requirements:

**Call from Python**

.. code-block:: python

    from gway import Gateway

    gway = Gateway()
    result = gway.awg.find_cable(meters=30, amps=60, material="cu", volts=240)
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

GWAY Website Server
~~~~~~~~~~~~~~~~~~~

You can also run a lightweight help/documentation server directly using GWAY:

.. code-block:: powershell

    PS C:\Users\arthe\Repos\gway> gway --debug website start-server --daemon - hold

This launches an interactive web UI that lets you browse your project, inspect help docs, and search callable functions.

Visit `http://localhost:8888` once it's running.

Online Help & Documentation
---------------------------

Browse built-in and project-level function documentation online at:

📘 https://arthexis.com

- Use the **search box** in the top left to find any callable by name (e.g., ``find_cable``, ``read_file``, ``parse_json``).
- You can also navigate directly to: ``https://arthexis.com/help/<project>/<function>`` or ``https://arthexis.com/help/<built-in>``

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
| scripts/       | GWAY script files (for --batch mode)                        |
+----------------+-------------------------------------------------------------+


After placing your modules under `projects/`, you can immediately invoke them with:

.. code-block:: bash

    gway my_module my_function --arg1 value


License
-------

MIT License
