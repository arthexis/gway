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
