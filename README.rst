GWAY
====

Gateway (``gw``) is a lightweight dispatcher that turns every Python function
into a command line entry.  It includes a recipe
runner so you can compose automations and simple web apps with only functions
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
- **Projects**: any ``.py`` file or directory inside ``projects/`` is loaded on demand. Nested modules use dotted notation (``gw.web.app.setup``).
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
- **Unquoted Kwargs**: values after ``--key`` may include spaces up to the next
  ``-`` or ``--`` token; quoting is optional.
- **Environment Loading**: ``envs/clients/<user>.env`` and
  ``envs/servers/<host>.env`` are read automatically.  A file can specify a
  ``BASE_ENV`` to inherit defaults from another file.
- **Async & Watchers**: coroutines are executed in background threads.  Use
   ``gw.until`` with file or URL watchers (and even PyPI version checks) to keep
   services running until a condition changes. PyPI version checks poll every
   30 minutes by default.
- **Web Helpers**: ``gw.web.app.setup`` registers views named ``view_*``
  (HTML), ``api_*`` (JSON) and ``render_*`` (fragments).  ``gw.web.server.start_app``
  launches a Bottle server.  Static assets live under ``data/static``.
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

   web app setup web.navbar --home style-changer
   web app setup web.site --home reader
   web server start-app --host 127.0.0.1 --port 8888
   until --done


Run ``gway -r recipes/site.gwr`` and visit ``http://127.0.0.1:8888`` to browse
help pages rendered by ``web.site.view_reader``.

Advanced Recipe Example
~~~~~~~~~~~~~~~~~~~~~~~

This example demonstrates the *colon* prefix for repeated commands and
``#`` lines used as notes. Indented entries inherit the prefix until the
next non-indented command.

.. code-block:: text

   # Configure multiple projects
   web app setup-app:
       - web.site --home reader
       - web.nav --style random --default-style dark-material.css
       - games.qpig --home qpig-farm

   # Start the server
   web:
    - static collect
    - server start-app --port 8888

   # Watch for file changes
   until --file work/reload.txt

Websites
~~~~~~~~

The ``web`` project assembles view functions into a small site. Register each
project with ``gw.web.app.setup`` and then launch the server using
``gw.web.server.start_app``. Routes of the form ``/project/view`` map to
``view_*`` functions and static files under ``data/static`` are served from
``/static``. ``web.site.view_reader`` renders ``.rst`` or ``.md`` files when
you visit ``/web/site/reader/PATH``; it first checks the workspace root and
then ``data/static`` automatically. See the `Web README
<https://arthexis.com/web/site/reader?tome=web>`_ for a more complete guide.

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

Project READMEs
---------------

Visit `/web/site/project-readmes`_ to browse the documentation bundled with
each project. The page is generated automatically using ``view_project_readmes``
so newly added README files appear without edits to this list.

You can generate these links yourself with
``gw.web.build_url('web/site/reader', tome='proj')``.

.. _/web/site/project-readmes: /web/site/project-readmes


License
-------

MIT License
