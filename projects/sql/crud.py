# file: projects/sql/crud.py
"""Generic SQL CRUD helpers using gw.sql."""

from gway import gw
import html


def api_create(*, table: str, dbfile=None, sql_engine="sqlite", project=None, **fields):
    """Insert a record into ``table`` and return the last row id."""
    assert table, "table required"
    with gw.sql.open_db(dbfile, sql_engine=sql_engine, project=project) as cur:
        columns = ", ".join(f'"{k}"' for k in fields)
        placeholders = ", ".join("?" for _ in fields)
        sql = f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})'
        cur.execute(sql, tuple(fields.values()))
        if sql_engine == "sqlite":
            cur.execute("SELECT last_insert_rowid()")
            row = cur.fetchone()
            return row[0] if row else None
    return None


def api_read(*, table: str, id, id_col: str = "id", dbfile=None, sql_engine="sqlite", project=None):
    """Return a single record by ``id``."""
    with gw.sql.open_db(dbfile, sql_engine=sql_engine, project=project) as cur:
        cur.execute(f'SELECT * FROM "{table}" WHERE "{id_col}" = ?', (id,))
        row = cur.fetchone()
    return row


def api_update(*, table: str, id, id_col: str = "id", dbfile=None, sql_engine="sqlite", project=None, **fields):
    """Update a record by ``id``."""
    with gw.sql.open_db(dbfile, sql_engine=sql_engine, project=project) as cur:
        assignments = ", ".join(f'"{k}"=?' for k in fields)
        sql = f'UPDATE "{table}" SET {assignments} WHERE "{id_col}" = ?'
        cur.execute(sql, tuple(fields.values()) + (id,))


def api_delete(*, table: str, id, id_col: str = "id", dbfile=None, sql_engine="sqlite", project=None):
    """Delete a record by ``id``."""
    with gw.sql.open_db(dbfile, sql_engine=sql_engine, project=project) as cur:
        cur.execute(f'DELETE FROM "{table}" WHERE "{id_col}" = ?', (id,))


def _table_columns(table: str, *, dbfile=None, sql_engine="sqlite", project=None):
    with gw.sql.open_db(dbfile, sql_engine=sql_engine, project=project) as cur:
        cur.execute(f'PRAGMA table_info("{table}")')
        rows = cur.fetchall()
    return [r[1] for r in rows]


def view_table(*, table: str, id_col: str = "id", dbfile=None, sql_engine="sqlite", project=None):
    """Simple HTML interface for listing and editing records."""
    from bottle import request, response

    with gw.sql.open_db(dbfile, sql_engine=sql_engine, project=project) as cur:
        if request.method == "POST":
            action = request.forms.get("action")
            if action == "create":
                fields = {
                    k: request.forms.get(k)
                    for k in _table_columns(table, dbfile=dbfile, sql_engine=sql_engine, project=project)
                    if k != id_col
                }
                api_create(table=table, dbfile=dbfile, sql_engine=sql_engine, project=project, **fields)
            elif action == "update":
                rid = request.forms.get(id_col)
                fields = {
                    k: request.forms.get(k)
                    for k in _table_columns(table, dbfile=dbfile, sql_engine=sql_engine, project=project)
                    if k != id_col
                }
                api_update(
                    table=table,
                    id=rid,
                    id_col=id_col,
                    dbfile=dbfile,
                    sql_engine=sql_engine,
                    project=project,
                    **fields,
                )
            elif action == "delete":
                rid = request.forms.get(id_col)
                api_delete(
                    table=table,
                    id=rid,
                    id_col=id_col,
                    dbfile=dbfile,
                    sql_engine=sql_engine,
                    project=project,
                )
            response.status = 303
            response.set_header("Location", request.fullpath)
            return ""

        cols = _table_columns(table, dbfile=dbfile, sql_engine=sql_engine, project=project)
        cur.execute(f'SELECT * FROM "{table}"')
        rows = cur.fetchall()
    head = "".join(f"<th>{html.escape(c)}</th>" for c in cols)
    body_rows = []
    for row in rows:
        cells = "".join(
            f"<td><input name='{c}' value='{html.escape(str(row[i]))}'></td>"
            for i, c in enumerate(cols)
        )
        r_id = row[cols.index(id_col)] if id_col in cols else ""
        body_rows.append(
            f"<tr><form method='post'>{cells}"\
            f"<td><input type='hidden' name='{id_col}' value='{html.escape(str(r_id))}'>"\
            "<button name='action' value='update'>Save</button> "\
            "<button name='action' value='delete'>Del</button></td></form></tr>"
        )
    new_inputs = "".join(f"<td><input name='{c}'></td>" for c in cols if c != id_col)
    create_row = (
        f"<tr><form method='post'>{new_inputs}"\
        f"<td><button name='action' value='create'>Add</button></td></form></tr>"
    )
    body_rows.append(create_row)
    body = "".join(body_rows)
    return f"<table><tr>{head}<th>Actions</th></tr>{body}</table>"

def view_setup_table(*, table: str, dbfile=None, sql_engine="sqlite", project=None):
    """HTML form for :func:`setup_table`. POST to add columns or drop."""
    from bottle import request, response

    if request.method == "POST":
        action = request.forms.get("action") or "add"
        if action == "drop":
            gw.sql.setup_table(table, None, drop=True, dbfile=dbfile, immediate=True)
        else:
            name = request.forms.get("name")
            ctype = request.forms.get("type") or "TEXT"
            if name:
                gw.sql.setup_table(table, name, ctype, dbfile=dbfile, immediate=True)
        response.status = 303
        response.set_header("Location", request.fullpath)
        return ""

    cols = []
    with gw.sql.open_db(dbfile, sql_engine=sql_engine, project=project) as cur:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if cur.fetchone():
            cur.execute(f"PRAGMA table_info([{table}])")
            cols = [(r[1], r[2]) for r in cur.fetchall()]

    rows = "".join(f"<tr><td>{html.escape(n)}</td><td>{html.escape(t)}</td></tr>" for n, t in cols)
    add_form = (
        "<form method='post'>"
        "<input name='name' placeholder='Column name'> "
        "<input name='type' placeholder='Type' value='TEXT'> "
        "<button>Add Column</button></form>"
    )
    drop_form = (
        (
            "<form method='post'>"
            "<input type='hidden' name='action' value='drop'>"
            "<button>Drop Table</button></form>"
        )
        if cols
        else ""
    )
    return f"<h1>{html.escape(table)}</h1><table>{rows}</table>{add_form}{drop_form}"
