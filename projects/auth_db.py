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

RFIDS = """rfids(
    rfid TEXT PRIMARY KEY,
    identity_id INTEGER,
    balance REAL,
    allowed INTEGER
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

def set_rfid(rfid, *, identity_id, balance=0.0, allowed=True, dbfile=None):
    m = _model(RFIDS, dbfile=dbfile)
    try:
        m.delete(rfid, id_col="rfid")
    except Exception:
        pass
    m.create(rfid=rfid, identity_id=identity_id, balance=balance, allowed=1 if allowed else 0)

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

def verify_rfid(rfid, *, dbfile=None):
    row = _model(RFIDS, dbfile=dbfile).read(rfid, id_col="rfid")
    if not row:
        return False, None
    if not bool(row[3]):
        return False, row[1]
    return True, row[1]

def get_balance(rfid, *, dbfile=None):
    row = _model(RFIDS, dbfile=dbfile).read(rfid, id_col="rfid")
    return float(row[2]) if row else 0.0

def adjust_balance(rfid, amount, *, dbfile=None):
    row = _model(RFIDS, dbfile=dbfile).read(rfid, id_col="rfid")
    if not row:
        return False
    new_bal = float(row[2]) + amount
    _model(RFIDS, dbfile=dbfile).update(rfid, id_col="rfid", balance=new_bal)
    return True

def get_identity(identity_id, *, dbfile=None):
    return _model(IDENTITIES, dbfile=dbfile).read(identity_id)
