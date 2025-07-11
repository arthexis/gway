SQL CRUD Helpers
----------------

The ``sql.crud`` project offers basic APIs for creating, reading,
updating and deleting records in any SQLite table. All functions use
``gw.sql.open_connection`` internally, so you can simply pass a
``--dbfile`` parameter (defaulting to ``work/data.sqlite``).

Example usage::

    from gway import gw
    item_id = gw.sql.crud.api_create(table='items', name='apple', qty=5)
    row = gw.sql.crud.api_read(table='items', id=item_id)
    gw.sql.crud.api_update(table='items', id=item_id, qty=10)
    gw.sql.crud.api_delete(table='items', id=item_id)

``view_table`` provides a simple HTML interface for editing a table.
Mount it with ``gw.web.app.setup_app``::

    gw.web.app.setup_app(project='sql.crud', home='table')

Then visit ``/sql/crud/table?table=items`` (add ``&dbfile=PATH`` if you
use a custom database file).

``setup_table`` can be used to create or extend a table schema::

    gw.sql.crud.setup_table(
        table='posts',
        columns={'id': 'INTEGER PRIMARY KEY', 'title': 'TEXT', 'body': 'TEXT'},
        dbfile='work/blog.sqlite'
    )

``view_setup_table`` exposes this functionality via the web interface so you
can add columns or drop a table through your browser.

The ``recipes/crud_site.gwr`` file shows how to combine this view with
``web.nav`` and ``web.site`` to create a minimal website.
