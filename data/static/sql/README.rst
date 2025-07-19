SQL CRUD Helpers
----------------

The ``sql.crud`` project offers basic APIs for creating, reading,
updating and deleting records in any SQLite table. All functions use
``gw.sql.open_db`` internally, so you can simply pass a
``--dbfile`` parameter (defaulting to ``work/data.sqlite``).

Schema changes are staged in memory until ``gw.sql.migrate`` is called.

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

``setup_table`` stages schema changes for later migration::

    gw.sql.setup_table('posts', 'id', 'INTEGER', primary=True, auto=True,
                       dbfile='work/blog.sqlite')
    gw.sql.setup_table('posts', 'title', 'TEXT', dbfile='work/blog.sqlite')
    gw.sql.setup_table('posts', 'body', 'TEXT', dbfile='work/blog.sqlite')
    gw.sql.migrate(dbfile='work/blog.sqlite')

``view_setup_table`` exposes this functionality via the web interface so you
can add columns or drop a table through your browser.

The ``recipes/midblog.gwr`` file shows how to combine this view with
``web.nav`` and ``web.site`` to create a minimal website.  For a slightly
more complete example with basic authentication see ``recipes/micro_blog.gwr``.

``gw.sql.model`` returns a proxy object with CRUD helpers for a specific
table. Pass an existing table name or a definition such as a mapping or
dataclass and the table will be created automatically::

    from dataclasses import dataclass
    from gway import gw

    @dataclass
    class Item:
        id: int
        name: str
        qty: int

    items = gw.sql.model(Item, dbfile='work/shop.sqlite')
    new_id = items.create(name='apple', qty=5)
    row = items.read(new_id)

You can also target other engines such as DuckDB::

    items = gw.sql.model(Item, dbfile='work/shop.duckdb', sql_engine='duckdb')

When using ``gw.sql.model`` in your own modules, define your table
specifications as uppercase constants and call ``gw.sql.model`` inside the
functions that operate on the data.  If the module also defines ``DBFILE`` and
``ENGINE`` constants they will be used automatically::

    DBFILE = 'work/blog.db'
    ENGINE = 'duckdb'

    POSTS = 'posts(id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT, body TEXT)'

    def add_post(title, body):
        gw.sql.model(POSTS).create(title=title, body=body)

