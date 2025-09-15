# file: projects/auth_db.py
"""Authentication database using gw.sql.model and DuckDB."""

from gway import gw
import base64

DBFILE = "work/auth.duckdb"
ENGINE = "duckdb"
PROJECT = "auth_db"

IDENTITIES = """identities(
    id INTEGER PRIMARY KEY,
    name TEXT
)"""

BASIC_AUTH = """basic_auth(
    username TEXT PRIMARY KEY,
    b64 TEXT,
    identity_id INTEGER
)"""

def _model(spec, *, dbfile=None):
    return gw.sql.model(spec, dbfile=dbfile or DBFILE, sql_engine=ENGINE, project=PROJECT)

def _next_identity_id(dbfile=None):
    # Ensure table exists before querying
    _model(IDENTITIES, dbfile=dbfile)
    conn = gw.sql.open_db(dbfile or DBFILE, sql_engine=ENGINE, project=PROJECT)
    rows = gw.sql.execute("SELECT max(id) FROM identities", connection=conn)
    max_id = rows[0][0] if rows and rows[0][0] is not None else 0
    return max_id + 1

def create_identity(name=None, *, dbfile=None):
    iid = _next_identity_id(dbfile)
    _model(IDENTITIES, dbfile=dbfile).create(id=iid, name=name)
    return iid

def set_basic_auth(username, password, *, identity_id, dbfile=None):
    pw_b64 = base64.b64encode(password.encode("utf-8")).decode("ascii")
    m = _model(BASIC_AUTH, dbfile=dbfile)
    try:
        m.delete(username, id_col="username")
    except Exception:
        pass
    m.create(username=username, b64=pw_b64, identity_id=identity_id)

def verify_basic(username, password, *, dbfile=None):
    row = _model(BASIC_AUTH, dbfile=dbfile).read(username, id_col="username")
    if not row:
        return False, None
    try:
        stored = base64.b64decode(row[1]).decode("utf-8")
    except Exception:
        return False, None
    if stored != password:
        return False, None
    return True, row[2]

def get_identity(identity_id, *, dbfile=None):
    return _model(IDENTITIES, dbfile=dbfile).read(identity_id)


def sync_from_url(url, *, dbfile=None, timeout=10):
    """Download a remote database and replace the local file."""
    import requests
    import os

    import pathlib

    target = pathlib.Path(gw.resource(dbfile or DBFILE))
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = target.with_name(target.name + ".tmp")
    gw.debug(f"[auth_db] fetching {url} -> {target}")
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    with open(tmp_path, "wb") as f:
        f.write(resp.content)
    os.replace(tmp_path, target)
    gw.info(f"[auth_db] synced {url}")
    return target
