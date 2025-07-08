GWAY
====

Gateway (``gw``) is a lightweight dispatcher that turns every Python function
into a command line entry.  It ships with a small set of helpers and a recipe
runner so you can compose automations and simple web apps with only functions
and ``.gwr`` files.

Quick Start
-----------

Install from PyPI or from source and invoke ``gway`` on the command line.
Every module inside ``projects/`` becomes a namespace on ``gw`` and a CLI
sub-command.

.. code-block:: bash

   gway hello-world
   gway awg find-cable --meters 30 --amps 60

.. code-block:: python

   from gway import gw
   gw.hello_world()
   result = gw.awg.find_cable(meters=30, amps=60)
   print(result["gauge"])

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
- **Projects**: any ``.py`` file or directory inside ``projects/`` is loaded on
demand.  Nested modules use dotted notation (``gw.web.app.setup``).
- **Builtins**: common utilities such as ``resource``, ``run_recipe``, ``help``,
  ``test`` and ``notify`` are always available.
- **Results & Context**: return values are stored in ``gw.results`` and are
  referenced by name.  Use sigils like ``[result.key]`` to pull values into
  later calls.
- **Sigils**: ``[VAR]`` or ``[object.attr]`` placeholders resolve from previous
  results, ``gw.context`` and environment variables.
- **Recipes** ``.gwr``: text files listing commands.  Indented lines reuse the
  previous command allowing very compact scripts.  Run them via
  ``gway -r file`` or ``gw.run_recipe('file.gwr')``.
- **Environment Loading**: ``envs/clients/<user>.env`` and
  ``envs/servers/<host>.env`` are read automatically.  A file can specify a
  ``BASE_ENV`` to inherit defaults from another file.
- **Async & Watchers**: coroutines are executed in background threads.  Use
  ``gw.until`` with file or URL watchers (and even PyPI version checks) to keep
  services running until a condition changes.
- **Web Helpers**: ``gw.web.app.setup`` registers views named ``view_*``
  (HTML), ``api_*`` (JSON) and ``render_*`` (fragments).  ``gw.web.server.start_app``
  launches a Bottle server.  Static assets live under ``data/static``.
- **Resources**: ``gw.resource`` resolves a file path in the workspace and can
  create files or directories.  ``gw.resource_list`` lists files matching
  filters.
- **Logging & Testing**: ``gw.setup_logging`` configures rotating logs in
  ``logs/``.  ``gway test --coverage`` or ``gw.test()`` run the suite.

Example Recipe
--------------

.. code-block:: text

   web app setup --project web.navbar --home style-changer
   web app setup --project web.site --home reader
   web server start-app --host 127.0.0.1 --port 8888
   until --forever


Run ``gway -r recipes/site.gwr`` and visit ``http://127.0.0.1:8888`` to browse
help pages rendered by ``web.site.view_reader``.

Folder Structure
----------------

Here's a quick reference of the main directories in a typical GWAY workspace:

+----------------+--------------------------------------------------------------+
| Directory      | Description                                                  |
+================+==============================================================+
| envs/clients/  | Per-user environment files (e.g., ``username.env``).         |
+----------------+--------------------------------------------------------------+
| envs/servers/  | Per-host environment files (e.g., ``hostname.env``).         |
+----------------+--------------------------------------------------------------+
| projects/      | Included GWAY python projects. You may add your own.        |
+----------------+--------------------------------------------------------------+
| logs/          | Runtime logs and log backups.                                |
+----------------+--------------------------------------------------------------+
| gway/          | Source code for core GWAY components.                        |
+----------------+--------------------------------------------------------------+
| tests/         | Unit tests for code in gway/ and projects/.                  |
+----------------+--------------------------------------------------------------+
| data/          | Static assets, resources, and other included data files.     |
+----------------+--------------------------------------------------------------+
| work/          | Working directory for output files and products.             |
+----------------+--------------------------------------------------------------+
| recipes/       | Included .gwr recipe files (-r mode). You may add more.      |
+----------------+--------------------------------------------------------------+
| tools/         | Platform-specific scripts and files.                         |
+----------------+--------------------------------------------------------------+

Websites
--------

The ``web`` project assembles view functions into a small site. Register each
project with ``gw.web.app.setup`` and then launch the server using
``gw.web.server.start_app``. Routes of the form ``/project/view`` map to
``view_*`` functions and static files under ``data/static`` are served from
``/static``. ``web.site.view_reader`` renders ``.rst`` or ``.md`` files when
you visit ``/site/reader/PATH``; it first checks the workspace root and
then ``data/static`` automatically. See the `Web README
</site/reader/web/README>`_ for a more complete guide.

Project READMEs
---------------

The following projects bundle additional documentation.  Each link uses
``view_reader`` to render the ``README.rst`` file directly from the
``data/static`` folder.

+------------+--------------------------------------------------------------+
| Project    | README                                                       |
+============+==============================================================+
| monitor    | `/site/reader/monitor/README`_           |
| ocpp       | `/site/reader/ocpp/README`_              |
| web        | `/site/reader/web/README`_               |
| games/qpig | `/site/reader/games/qpig/README`_        |
+------------+--------------------------------------------------------------+

You can generate these links yourself with
``gw.web.app.build_url('reader', 'proj/README')``.

License
-------

MIT License
