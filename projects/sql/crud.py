# file: projects/sql/crud.py
"""Generic SQL CRUD helpers using gw.sql."""

from gway import gw
import html


def api_create(*, table: str, dbfile=None, **fields):
    """Insert a record into ``table`` and return the last row id."""
    assert table, "table required"
    with gw.sql.open_connection(dbfile) as cur:
        columns = ", ".join(f"[{k}]" for k in fields)
        placeholders = ", ".join("?" for _ in fields)
        sql = f"INSERT INTO [{table}] ({columns}) VALUES ({placeholders})"
        cur.execute(sql, tuple(fields.values()))
        cur.execute("SELECT last_insert_rowid()")
        row = cur.fetchone()
    return row[0] if row else None


def api_read(*, table: str, id, id_col: str = "id", dbfile=None):
    """Return a single record by ``id``."""
    with gw.sql.open_connection(dbfile) as cur:
        cur.execute(f"SELECT * FROM [{table}] WHERE [{id_col}] = ?", (id,))
        row = cur.fetchone()
    return row


def api_update(*, table: str, id, id_col: str = "id", dbfile=None, **fields):
    """Update a record by ``id``."""
    with gw.sql.open_connection(dbfile) as cur:
        assignments = ", ".join(f"[{k}]=?" for k in fields)
        sql = f"UPDATE [{table}] SET {assignments} WHERE [{id_col}] = ?"
        cur.execute(sql, tuple(fields.values()) + (id,))


def api_delete(*, table: str, id, id_col: str = "id", dbfile=None):
    """Delete a record by ``id``."""
    with gw.sql.open_connection(dbfile) as cur:
        cur.execute(f"DELETE FROM [{table}] WHERE [{id_col}] = ?", (id,))


def _table_columns(table: str, *, dbfile=None):
    with gw.sql.open_connection(dbfile) as cur:
        cur.execute(f"PRAGMA table_info([{table}])")
        rows = cur.fetchall()
    return [r[1] for r in rows]


def view_table(*, table: str, id_col: str = "id", dbfile=None):
    """Simple HTML interface for listing and editing records."""
    from bottle import request, response

    with gw.sql.open_connection(dbfile) as cur:
        if request.method == "POST":
            action = request.forms.get("action")
            if action == "create":
                fields = {k: request.forms.get(k) for k in _table_columns(table, dbfile=dbfile) if k != id_col}
                api_create(table=table, dbfile=dbfile, **fields)
            elif action == "update":
                rid = request.forms.get(id_col)
                fields = {k: request.forms.get(k) for k in _table_columns(table, dbfile=dbfile) if k != id_col}
                api_update(table=table, id=rid, id_col=id_col, dbfile=dbfile, **fields)
            elif action == "delete":
                rid = request.forms.get(id_col)
                api_delete(table=table, id=rid, id_col=id_col, dbfile=dbfile)
            response.status = 303
            response.set_header("Location", request.path_qs)
            return ""

        cols = _table_columns(table, dbfile=dbfile)
        cur.execute(f"SELECT * FROM [{table}]")
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
