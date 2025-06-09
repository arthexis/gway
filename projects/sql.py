# projects/sql.py

import os
import csv
import sqlite3
import threading
from gway import gw

# # GWAY database functions. These can be called from anywhere safely:
#
# from gway import gw
#
# with gw.sql.open_connection() as cursor:
#      gq.sql.execute(query)
#
# # Or from a recipe:
#
# sql connect
# sql execute "<SQL>"
#

class WrappedConnection:
    def __init__(self, connection):
        self._connection = connection
        self._cursor = None

    def __enter__(self):
        self._cursor = self._connection.cursor()
        return self._cursor

    def __exit__(self, exc_type, *_):
        if exc_type is None:
            self._connection.commit()
            gw.debug("Transaction committed.")
        else:
            self._connection.rollback()
            gw.warning("Transaction rolled back due to exception.")
        self._cursor = None

    def __getattr__(self, name):
        return getattr(self._connection, name)


def infer_type(val):
    return gw.infer_type(
        val,
        INTEGER=int,
        REAL=float
    ) or "TEXT"


def load_csv(*, connection=None, folder="data", force=False):
    """
    Recursively loads CSVs from a folder into SQLite tables.
    Table names are derived from folder/file paths.
    """
    assert connection
    base_path = gw.resource(folder)

    def load_folder(path, prefix=""):
        cursor = connection.cursor()
        for item in os.listdir(path):
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                sub_prefix = f"{prefix}_{item}" if prefix else item
                load_folder(full_path, sub_prefix)
            elif item.endswith(".csv"):
                base_name = os.path.splitext(item)[0]
                table_name = f"{prefix}_{base_name}" if prefix else base_name
                table_name = table_name.replace("-", "_")

                with open(full_path, "r", encoding="utf-8") as f:
                    reader = csv.reader(f)
                    try:
                        headers = next(reader)
                        sample_row = next(reader)
                    except StopIteration:
                        gw.warning(f"Skipping empty CSV: {full_path}")
                        continue

                    seen = set()
                    unique_headers = []
                    for h in headers:
                        h_clean = h.strip()
                        h_final = h_clean
                        i = 1
                        while h_final.lower() in seen:
                            h_final = f"{h_clean}_{i}"
                            i += 1
                        unique_headers.append(h_final)
                        seen.add(h_final.lower())

                    types = [
                        infer_type(sample_row[i])
                        if i < len(sample_row) else "TEXT"
                        for i in range(len(unique_headers))
                    ]

                    cursor.execute(
                        "SELECT name FROM sqlite_master "
                        "WHERE type='table' AND name=?", (table_name,)
                    )
                    exists = cursor.fetchone()

                    if exists and force:
                        cursor.execute(f"DROP TABLE IF EXISTS [{table_name}]")
                        gw.info(f"Dropped existing table: {table_name}")

                    if not exists or force:
                        colspec = ", ".join(
                            f"[{unique_headers[i]}] {types[i]}"
                            for i in range(len(unique_headers))
                        )
                        create = f"CREATE TABLE [{table_name}] ({colspec})"
                        insert = (
                            f"INSERT INTO [{table_name}] "
                            f"({', '.join(f'[{h}]' for h in unique_headers)}) "
                            f"VALUES ({', '.join('?' for _ in unique_headers)})"
                        )

                        cursor.execute(create)
                        cursor.execute(insert, sample_row)
                        cursor.executemany(insert, reader)
                        connection.commit()

                        gw.info(
                            f"Loaded table '{table_name}' with "
                            f"{len(unique_headers)} columns"
                        )
                    else:
                        gw.debug(f"Skipped existing table: {table_name}")
        cursor.close()

    load_folder(base_path)


_connection_cache = {}

def open_connection(datafile=None, *, 
            sql_engine="sqlite", autoload=False, force=False,
            row_factory=False, **dbopts):
    """
    Initialize or reuse a database connection.
    Caches connections by sql_engine, file path, and thread ID (if required).
    """

    # Determine base cache key
    base_key = (sql_engine, datafile or "default")

    # Determine if thread ID should be included in key
    if sql_engine in {"sqlite"}:
        thread_key = threading.get_ident()
    else:
        thread_key = "*"

    key = (base_key, thread_key)

    if key in _connection_cache:
        conn = _connection_cache[key]
        if row_factory:
            gw.warning("Row factory change requires close_connection(). Reconnect manually.")
        gw.debug(f"Reusing connection: {key}")
        return conn

    # Create connection
    if sql_engine == "sqlite":
        path = gw.resource(datafile or "work/data.sqlite")
        conn = sqlite3.connect(path)

        if row_factory:
            if row_factory is True:
                conn.row_factory = sqlite3.Row
            elif callable(row_factory):
                conn.row_factory = row_factory
            elif isinstance(row_factory, str):
                conn.row_factory = gw[row_factory]
            gw.debug(f"Configured row_factory: {conn.row_factory}")

        gw.info(f"Opened SQLite connection at {path}")

    elif sql_engine == "duckdb":
        import duckdb
        path = gw.resource(datafile or "work/data.duckdb")
        conn = duckdb.connect(path)
        gw.info(f"Opened DuckDB connection at {path}")

    elif sql_engine == "postgres":
        import psycopg2
        conn = psycopg2.connect(**dbopts)
        gw.info(f"Connected to Postgres at {dbopts.get('host', 'localhost')}")

    else:
        raise ValueError(f"Unsupported sql_engine: {sql_engine}")

    # Wrap and cache connection
    conn = WrappedConnection(conn)
    _connection_cache[key] = conn

    if autoload and sql_engine == "sqlite":
        load_csv(connection=conn, force=force)

    return conn


def close_connection(datafile=None, *, sql_engine="sqlite", all=False):
    """
    Explicitly close one or all cached database connections.
    """
    if all:
        for connection in _connection_cache.values():
            try:
                connection.close()
            except Exception as e:
                gw.warning(f"Failed to close connection: {e}")
        _connection_cache.clear()
        gw.info("All connections closed.")
        return

    key = (sql_engine, datafile or "default")
    connection = _connection_cache.pop(key, None)
    if connection:
        try:
            connection.close()
            gw.info(f"Closed connection: {key}")
        except Exception as e:
            gw.warning(f"Failed to close {key}: {e}")


def execute(*sql, connection=None, script=None, sep='; '):
    """
    Execute SQL code or a script resource. If both are given, run script first.
    """
    assert execute, "Call gw.sql.open_connection first()"

    if sql:
        sql = sep.join(sql)

    cursor = connection.cursor()

    try:
        if script:
            script_text = gw.resource(script, text=True)
            cursor.executescript(script_text)
            gw.info(f"Executed script from: {script}")

        if sql:
            cursor.execute(sql)
            return cursor.fetchall() if cursor.description else None
    finally:
        cursor.close()

