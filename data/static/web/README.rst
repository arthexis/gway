Web Project Notes
-----------------

* `setup_app` can be invoked multiple times. Each call adds routes and homes for a single project.
* Routes are registered with `add_route`, which skips duplicates so repeated setups won't register the same handler twice.
* If the added project defines its own ``setup_app`` function, it is invoked with the app object.
* Extra keyword arguments are passed to that project's ``setup_app``. If no such function exists, the unused argument names are logged as an error.
* ``web.nav`` supports ``--style`` to force a theme; pass ``random`` to pick a different theme each request.
* When reusing `setup_app`, provide unique paths or homes to avoid collisions.
* CLI flags resolve to a single value. Lists like ``--home a,b,c`` are not supported. Call the command once per value instead.
* `web.site.view_reader` serves ``.md`` or ``.rst`` files from the resource root and can be used for a lightweight blog. Subfolders and hidden files are not allowed.

View and Render
---------------

The ``web.app`` project registers view and render routes for all projects.
To obtain just the HTML fragment produced by a view without the surrounding
layout, request ``/render/<project>/<view>``.

Parameters are handled exactly like the regular ``/project/view`` route, so you
can use GET or POST to pass values. Returned content is suitable for dynamic
insertion via ``render.js`` or inclusion in an ``iframe``.

``render.js`` also supports manual refresh hooks:

- ``gw-click``/``gw-left-click`` – refresh on left click.
- ``gw-right-click`` – refresh on right click.
- ``gw-double-click`` – refresh on double click.
- ``gw-on-load`` – refresh once when the page loads.

Double clicking the QR compass in the sidebar triggers a dynamic refresh via
``render.js`` if the active project provides a ``render_compass`` function.

For example, to embed the ``reader`` page:

.. code-block:: html

   <iframe src="https://your.domain.com/render/web/site/reader?title=README"></iframe>

Only self-contained views display correctly when framed.

