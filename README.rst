GWAY
====

Welcome, this is the GWAY project README file and demo website.

**GWAY** is a CLI and function-dispatch framework that allows you to invoke and chain Python functions from your own projects or built-ins, with sigil in-context resolution, argument injection, control inversion, auto-wired recipes and multi-environment support. GWAY is async-compatible and fully instrumented.

`Our Goal: Lower the barrier to a higher-level of systems integration.`

`Our Approach: Every function is an entry point and can be a full solution.`

Fetch the source, changelogs and issues (or submit your own) here:

https://github.com/arthexis/gway

See a demo and the full list of available projects and other help topics online here:

https://arthexis.com/site/help

Basic Features
--------------

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

https://arthexis.com/awg/cable-finder


GWAY Website Server
~~~~~~~~~~~~~~~~~~~

You can also run a bundled lightweight help/documentation server using a GWAY Recipe:

.. code-block:: powershell

    > gway -r website

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
- You can also navigate directly to: ``https://arthexis.com/gway/help?topic=<project-or-function>``

This is useful for both the included out-of-the-box GWAY tools and your own projects, assuming they follow the GWAY format.


Installation
------------

Your chosen Installation method will depend on how you intend to use GWAY:

1. If you intend to contribute to GWAY at some point or want to access the latest updates from the open source community, you should **Install from Source**. As a plus, you get everything in the basic ecosystem from the get go.
2. If you want to use GWAY for a private use, such as work for a company or customer that prevents you from sharing your code, or you already have an open-source repo but want a second personal one, **Install via PyPI**.

You may also install them either way and just experiment with what each mode offers. For example, PyPI install allows you to easily use GWAY within Google Colab or other IPython/Jupyter projects.

Install via PyPI:

.. code-block:: bash

    pip install gway


# TODO: Explain configuration of the local GWAY_ROOT directory


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

To run GWAY automatically as a service using a recipe:

.. code-block:: bash

    sudo ./install.sh <recipe>   # On Linux/macOS
    install.bat <recipe>         # On Windows

On Windows, the installed service will automatically restart if it exits
unexpectedly.

This pulls the latest updates from the `main` branch and refreshes dependencies.

To make GWAY available from any directory (requires root access):

.. code-block:: bash

    sudo ln -s "$HOME/gway/gway.sh" /usr/local/bin/gway


Project Structure
-----------------

Here's a quick reference of the main directories in a typical GWAY workspace:

+----------------+-------------------------------------------------------------+
| Directory      | Description                                                 |
+================+=============================================================+
| envs/clients/  | Per-user environment files (e.g., ``username.env``).        |
+----------------+-------------------------------------------------------------+
| envs/servers/  | Per-host environment files (e.g., ``hostname.env``).        |
+----------------+-------------------------------------------------------------+
| projects/      | Included GWAY python projects. You may add your own.        |
+----------------+-------------------------------------------------------------+
| logs/          | Runtime logs and log backups.                               |
+----------------+-------------------------------------------------------------+
| gway/          | Source code for core GWAY components.                       |
+----------------+-------------------------------------------------------------+
| tests/         | Unit tests for code in gway/ and projects/.                 |
+----------------+-------------------------------------------------------------+
| data/          | Static assets, resources, and other included data files.    |
+----------------+-------------------------------------------------------------+
| work/          | Working directory for output files and products.            |
+----------------+-------------------------------------------------------------+
| recipes/       | Included .gwr recipe files (-r mode). You may add more.     |
+----------------+-------------------------------------------------------------+
| tools/         | Platform-specific scripts and files.                        |
+----------------+-------------------------------------------------------------+


After placing your modules under `projects/`, you can immediately invoke them from the CLI with:

.. code-block:: bash

    gway project-dir-or-script your-function argN --kwargN valueN


By default, results get reused as context for future calls made with the same Gateway thread.  


Recipes and Web Views
=====================

GWAY comes with powerful primitives for building modular web applications out of ordinary Python functions. 
You can declare site structure and custom views with just a few lines of code, and compose complex sites by chaining projects.

Overview
--------

- **Views** are simply Python functions in a project (e.g. `projects/web/site.py`) named according to a pattern (by default, `view_{name}`).
- The `web.app.setup` function registers views from one or more projects and sets up all routing and static file handling.
- The `web.server.start-app` function launches your site on a local server using Bottle (or FastAPI, for ASGI).
- All configuration can be scripted using GWAY recipes (`.gwr` files) for full automation.

Minimal Example
---------------

Suppose you want to create a very simple website:

.. code-block:: python

    # projects/mysite.py

    def view_hello():
        return "<h1>Hello, World!</h1>"

    def view_about():
        return "<h2>About This Site</h2><p>Powered by GWAY.</p>"

    def view_user(*, user_id=None):
        if user_id:
            # We have a user_id, so greet the user
            return f"<h1>Welcome {user_id}</h1>"
        else:
            # No user_id, so render a form to collect it
            return '''
            <form method="get" action="">
                <label for="user_id">Enter User ID:</label>
                <input type="text" id="user_id" name="user_id" required />
                <button type="submit">Submit</button>
            </form>
            '''

Note that these views don't need to be decorated and you don't have to return the entire HTML document. You also don't have to specify http methods or where the variables come from (they can be read from a form or passed as a query param.) 

Then in your own recipe:

.. code-block:: text

    # recipes/my-website.gwr
    web app setup --project mysite --home hello
    web app setup --project web.navbar
    web server start-app --host 127.0.0.1 --port 8888
    forever

Navigate to http://127.0.0.1:8888/mysite/hello or /mysite/about to see your views, including a handy navbar. Press Ctrl+D or close the terminal to end the process.

The **forever** function keeps the above apps and servers running forever.


Composing Sites from Multiple Projects
--------------------------------------

You can chain as many projects as you want; each can define its own set of views and home page:

.. code-block:: text

    # recipes/my-website.gwr
    web app setup --home readme
        --project web.cookie 
        --project web.navbar --home style-changer
        --project vbox --home uploads
        --project conway --home game-of-life --path games/conway

    web server start-app --host 127.0.0.1 --port 8888
    until --file VERSION --pypi


The above example combines basic features such as cookies and navbar with custom projects, a virtual upload/download box system and Conway's Game of Life, into a single application. 

The above recipe also shows implicit repeated commands. For example, instead of writing "web app setup" multiple times, each line below that doesn't start with a command repeats the last command with new parameters.

The **until** function, as used here, will keep the recipe going until the package updates in PyPI (checked hourly) or a manual update ocurrs. This is appropriate for self-restarting services such as those managed by systemd or kubernetes.



How It Works
------------

- `web.app.setup` wires up each project, registering all views (functions starting with the given prefix, default `view_`).
- You call setup multiple times to configure each project. The project/function name can be skipped on repeat lines.
- Each project can declare a "home" view, which becomes the landing page for its route.
- Static files are served from your `data/static/` directory and are accessible at `/static/filename`.
- The routing system matches `/project/viewname` to a function named `view_viewname` in the relevant project.
- Query parameters and POST data are automatically passed as keyword arguments to your view function.

View Example with Arguments
---------------------------

.. code-block:: python

    # projects/vbox.py

    def view_uploads(*, vbid: str = None, timeout: int = 60, files: int = 4, email: str = None, **kwargs):
        """
        GET: Display upload interface or create a new upload box.
        POST: Handle uploaded files to a specific vbid.
        """
        ...

This view can be accessed as `/vbox/uploads` and will receive POST or GET parameters as arguments. 

Recipes make Gway scripting modular and composable. Include them in your automation flows for maximum reuse and clarity.


Design Philosophies
===================

This section contains notes from the author that **may** provide insight to future developers.


Keep a Goal in Mind by Making it a TODO
---------------------------------------

Before you start writing any code, even if you have already planned the feature in an external system, write a # TODO comment explaining the required changes in as much detail as you need to define it unambiguously.

TODOs should live with the code they intend to affect. They warn that things are going to soon be different. It allows a good feature to be noted instead of lost to priorities. Keeping the tasks in the code itself as TODOs is superior to using an external tool. Those systems should look at the code as the source of truth to determine what TODOs need to be accomplished and make them more visible instead.

However, if a TODO affects the entire project, put it at the top of the file instead.

You may write the TODO and then dispatch it in the same coding session, or it may live on for many commits until its time comes. Or maybe you change your mind and delete the TODO. You get a space, close to the code, where you can see the effects of what you intend to integrate next.


On Comments and the Code that Binds Them
----------------------------------------

Comments and code should be like DNA — two strings that reflect each other.

This reflection creates a form of internal consistency and safety. When code and its comments are in alignment, they mutually verify each other.
When they diverge, the inconsistency acts as a warning sign: something is broken, outdated, or misunderstood.

Treat comments not as annotations, but as the complementary strand of the code itself. Keep them synchronized. A mismatch is not a small issue — it's a mutation worth investigating.


The Holy Hand Grenade of Antioch Procedure
------------------------------------------

If there is *not* only one good way to do it, then you should have **three**.

**Five is right out.**

One way implies clarity. Two implies division. Three implies depth. Five implies confusion, and confusion leads to bugs. When offering choices — in interface, design, or abstraction — ensure there are no more than three strong forms. The third may be unexpected, but it must still be necessary.

Beyond that, you're just multiplying uncertainty. This same principle applies to other aspects of coding. A simple function fits a single IDE screen. A complex one may span three. Five means: refactor this.


License
-------

MIT License
