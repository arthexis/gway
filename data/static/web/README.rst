Web Project Notes
-----------------

* `setup_app` can be invoked multiple times. Each call adds routes and homes for a single project.
* Routes are registered with `add_route`, which skips duplicates so repeated setups won't register the same handler twice.
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

For example, to embed the ``reader`` page:

.. code-block:: html

   <iframe src="https://your.domain.com/render/site/reader?title=README"></iframe>

Only self-contained views display correctly when framed.

