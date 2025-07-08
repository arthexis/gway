Web Project Notes
-----------------

* `setup_app` can be invoked multiple times. Each call adds routes and homes for a single project.
* Routes are registered with `add_route`, which skips duplicates so repeated setups won't register the same handler twice.
* When reusing `setup_app`, provide unique paths or homes to avoid collisions.
* CLI flags resolve to a single value. Lists like ``--home a,b,c`` are not supported. Call the command once per value instead.
* `web.site.view_reader` serves ``.md`` or ``.rst`` files from the resource root and can be used for a lightweight blog. Subfolders and hidden files are not allowed.
