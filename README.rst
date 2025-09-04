GWAY
====

Gateway (``gw``) is a lightweight dispatcher that turns every Python function
into a command line entry.  It includes a recipe
runner so you can compose automations with only functions
and ``.gwr`` files.

Quick Start
-----------

Install from PyPI or from source and invoke ``gway`` on the command line.
Every module inside ``projects/`` becomes a namespace on ``gw`` and a CLI
sub-command.

.. code-block:: bash

   gway hello-world
   gway awg find-awg --meters 30 --amps 60

.. code-block:: python

   from gway import gw
   gw.hello_world()
   result = gw.awg.find_awg(meters=30, amps=60)
   print(result["awg"])

Installation
------------

``pip install gway`` pulls the latest released package from PyPI. Use this
when you simply want to depend on GWAY in your own projects.  To work on the
framework itself clone the repository and install it in editable mode:

.. code-block:: bash

   git clone https://github.com/arthexis/gway.git
   cd gway
   pip install -r requirements.txt
   pip install -e .

Core Concepts
-------------

- **Gateway Object** ``gw``: entry point for all operations.  Calling
  ``gw.project.func()`` is equivalent to ``gway project func``.
- **Projects**: any ``.py`` file or directory inside ``projects/`` is loaded on demand. Nested modules use dotted notation.
- **Builtins**: common utilities such as ``resource``, ``run_recipe``, ``help``,
  ``test`` and ``notify`` are always available.
- **Results & Context**: return values are stored in ``gw.results`` and are
  referenced by name.  Use sigils like ``[result.key]`` to pull values into
  later calls.
- **Sigils**: ``[VAR]`` or ``[object.attr]`` placeholders resolve from previous
  results, ``gw.context`` and environment variables. Automatic resolution only
  happens for sigils prefixed with ``%`` (e.g. ``%[VAR]``); other sigils remain
  lazy until passed to ``gw.resolve`` or ``gw["VAR"]``.
- **Recipes** ``.gwr``: text files listing commands.  Indented lines reuse the
  previous command allowing very compact scripts.  Run them via
  ``gway -r file`` or ``gw.run_recipe('file.gwr')``.
- **Unquoted Kwargs**: values after ``--key`` may include spaces up to the next
  ``-`` or ``--`` token; quoting is optional.
- **Environment Loading**: ``envs/clients/<user>.env`` and
  ``envs/servers/<host>.env`` are read automatically.  A file can specify a
  ``BASE_ENV`` to inherit defaults from another file.
- **Async & Watchers**: coroutines are executed in background threads.  Use
   ``gw.until`` with file or URL watchers (and even PyPI version checks) to keep
   services running until a condition changes. PyPI version checks poll every
   30 minutes by default.
- **Resources**: ``gw.resource`` resolves a file path in the workspace and can
  create files or directories.  ``gw.resource_list`` lists files matching
  filters.
- **Logging & Testing**: ``gw.setup_logging`` configures rotating logs in
  ``logs/``.  ``gway test --coverage`` or ``gw.test()`` run the suite.

Recipes
-------

Recipes are ``.gwr`` files listing commands to automate tasks. Run them with
``gway -r file`` or ``gw.run_recipe('file.gwr')``.

Example Basic Recipe
~~~~~~~~~~~~~~~~~~~~

.. code-block:: text

       awg awg-probe --target localhost
       auth-db load sample.cdv


Folder Structure

Here's a quick reference of the main directories in a typical GWAY workspace:

+----------------+--------------------------------------------------------------+
| Directory      | Description                                                  |
+================+==============================================================+
| envs/clients/  | Per-user environment files (e.g., ``username.env``).         |
+----------------+--------------------------------------------------------------+
| envs/servers/  | Per-host environment files (e.g., ``hostname.env``).         |
+----------------+--------------------------------------------------------------+
| projects/      | Included GWAY python projects. You may add your own.         |
+----------------+--------------------------------------------------------------+
| logs/          | Runtime logs and log backups.                                |
+----------------+--------------------------------------------------------------+
| gway/          | Source code for core GWAY components.                        |
+----------------+--------------------------------------------------------------+
| tests/         | Hierarchical unit tests (e.g., ``tests/gway``).              |
+----------------+--------------------------------------------------------------+
| data/          | Static assets, resources, and other included data files.     |
+----------------+--------------------------------------------------------------+
| work/          | Working directory for output files and products.             |
+----------------+--------------------------------------------------------------+
| recipes/       | Included .gwr recipe files (-r mode). You may add more.      |
+----------------+--------------------------------------------------------------+
| tools/         | Platform-specific scripts and files.                         |
+----------------+--------------------------------------------------------------+

Testing
-------

The test suite verifies projects using the ``gw`` dispatcher. Install all
dependencies and run ``gway test`` to execute it.

Test Layout
~~~~~~~~~~~
Tests are discovered recursively so directories under ``tests`` may mirror the source tree. A suggested structure is::

    tests/
        gway/
        projects/

Running Tests
~~~~~~~~~~~~~

Before executing the suite, ensure the package and all dependencies are installed. Follow the commands in ``TESTING.rst`` to install ``requirements.txt`` and the editable package, then invoke ``gway test``.


License
-------

MIT License
