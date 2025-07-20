Web Navigation
--------------

JavaScript helpers for responsive navigation menus.

``web.nav`` accepts a ``--style`` parameter during setup to select the
initial theme without exposing the style switcher. Use ``--style random``
to pick a random theme on each request. A ``--side top`` option places the
navigation bar at the top of the page with drop-down menus.
The style switcher drop-down also includes a **Random** option to toggle
this behavior per user. ``--default-style`` (or ``--default_css``) changes
the fallback theme used when no preference is stored.

The style switcher page previews the selected theme and now showcases
several common inputs such as text fields, checkboxes, radio buttons and
a select drop-down to demonstrate how each style affects form elements.
