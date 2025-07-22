Web Project Notes
-----------------

* `setup_app` can be invoked multiple times. Each call adds routes and homes for a single project.
* Routes are registered with `add_route`, which skips duplicates so repeated setups won't register the same handler twice.
* If the added project defines its own ``setup_app`` function, it is invoked with the app object.
* Extra keyword arguments are passed to that project's ``setup_app``. If no such function exists, the unused argument names are logged as an error.
* Sub‑projects are automatically searched for view, API and render functions.
  Additional ``delegates`` can be specified to include other projects as fallback modules.
* ``web.nav`` supports ``--style`` to force a theme; pass ``random`` to pick a different theme each request.
* When reusing `setup_app`, provide unique paths or homes to avoid collisions.
* CLI flags resolve to a single value. Lists like ``--home a,b,c`` are not supported. Call the command once per value instead.
* `web.site.view_reader` serves ``.md`` or ``.rst`` files from the resource root and can be used for a lightweight blog. Subfolders and hidden files are not allowed.
* Footer links should be configured via the ``--footer`` option or template designs. The ``web.footer`` project renders them. Avoid editing ``render_footer_links`` directly to inject items, as that may cause duplicates like the ``Gateway Cookbook`` link.

View and Render
---------------

The ``web.app`` project registers view and render routes for all projects.
To obtain just the HTML fragment produced by a view without the surrounding
layout, request ``/render/<project>/<view>``.

Parameters are handled exactly like the regular ``/project/view`` route, so you
can use GET or POST to pass values. Returned content is suitable for dynamic
insertion via ``render.js`` or inclusion in an ``iframe``.

``render.js`` also supports manual refresh hooks and a lightweight API helper.

- ``gw-click``/``gw-left-click`` – refresh on left click.
- ``gw-right-click`` – refresh on right click.
- ``gw-double-click`` – refresh on double click.
- ``gw-on-load`` – refresh once when the page loads.
- ``gw-render`` – refresh using the named ``render_*`` function. If the element
  is or contains a form, fields are posted along with data attributes.
- ``gw-view`` – call the named ``view_*`` function without the page layout. Form
  values are sent just like ``gw-render``.
- ``gw-api`` – call the named ``api_*`` function and replace any ``[sigils]``
  in the element with values from the JSON response. If the element is a form,
  or contains one, form fields are posted as parameters. A different form can
  be specified with ``gw-form``.

Double clicking the QR compass in the sidebar triggers a dynamic refresh via
``render.js`` if the active project provides a ``render_compass`` function.

For example, to embed the ``reader`` page:

.. code-block:: html

   <iframe src="https://your.domain.com/render/web/site/reader?title=README"></iframe>

Only self-contained views display correctly when framed.

Function Naming and Routing
---------------------------

Functions prefixed with ``view_`` render HTML pages. ``api_`` functions return
JSON and ``render_`` functions return fragments for dynamic updates. Their names
map directly to URL paths:

* ``view_home`` -> ``/project/home``
* ``view_get_stats`` -> ``/project/stats`` for GET requests only
* ``api_update`` -> ``/api/project/update``
* ``render_status_charger`` -> ``/render/project/status/charger``

Multiple views may be combined in one request using ``+`` in the path, e.g.
``/project/view1+view2``. Render functions can return HTML strings, JSON lists
or dictionaries and are often used with ``render.js`` for auto-refresh blocks.

Static Collection
-----------------

``setup_app`` bundles CSS and JavaScript from enabled projects into
``/shared/global.css`` and ``/shared/global.js``. Call ``web static collect``
before starting the server to create or update these bundles. To add files for a
specific view, create ``<view>.css`` or ``<view>.js`` (without the ``view_``
prefix) inside ``data/static/<project>``. These assets are picked up
automatically during ``static collect`` so manual ``<link>`` or ``<script>``
tags are unnecessary unless ``mode='manual'`` is requested.

