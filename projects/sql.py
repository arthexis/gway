# projects/sql.py

import os
import csv
import queue
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
#   - execute "<SQL>"

_write_queue = queue.Queue()
_writer_thread = None
_writer_shutdown = threading.Event()

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

    def cursor(self):
        return self._connection.cursor()

    def commit(self):
        return self._connection.commit()

    def rollback(self):
        return self._connection.rollback()

    def close(self):
        return self._connection.close()


def infer_type(val):
    t, _ = gw.try_cast(val, INTEGER=int, REAL=float)
    return t or "TEXT"


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


# --- Connection Management (Drop-in Replacement) ---

_connection_cache = {}

def open_connection(
        datafile=None, *, 
        sql_engine="sqlite", autoload=False, force=False, row_factory=False, **dbopts):
    """
    Initialize or reuse a database connection.
    Caches connections by sql_engine, file path, and thread ID (if required).
    Starts writer thread for SQLite.
    """
    # Build cache key (engine, datafile, thread)
    _start_writer_thread()
    base_key = (sql_engine, datafile or "default")
    thread_key = threading.get_ident() if sql_engine == "sqlite" else "*"
    key = (base_key, thread_key)

    # Reuse cached connection if available
    if key in _connection_cache:
        conn = _connection_cache[key]
        if row_factory:
            gw.warning("Row factory change requires close_connection(). Reconnect manually.")
        gw.debug(f"Reusing connection: {key}")
        return conn

    # Create connection per backend
    if sql_engine == "sqlite":
        path = gw.resource(datafile or "work/data.sqlite")
        # Note: check_same_thread=False for sharing connections in the writer thread
        conn = sqlite3.connect(path, check_same_thread=False)
        if row_factory:
            if row_factory is True:
                conn.row_factory = sqlite3.Row
            elif callable(row_factory):
                conn.row_factory = row_factory
            elif isinstance(row_factory, str):
                conn.row_factory = gw[row_factory]
            gw.debug(f"Configured row_factory: {conn.row_factory}")
        gw.info(f"Opened SQLite connection at {path}")
        _start_writer_thread()  # Ensure writer is running
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
    Shuts down writer thread if all connections closed.
    """
    if all:
        for key, connection in list(_connection_cache.items()):
            try:
                connection.close()
            except Exception as e:
                gw.warning(f"Failed to close connection: {e}")
            _connection_cache.pop(key, None)
        shutdown_writer()
        gw.info("All connections closed.")
        return

    base_key = (sql_engine, datafile or "default")
    thread_key = threading.get_ident() if sql_engine == "sqlite" else "*"
    key = (base_key, thread_key)
    connection = _connection_cache.pop(key, None)
    if connection:
        try:
            connection.close()
            gw.info(f"Closed connection: {key}")
        except Exception as e:
            gw.warning(f"Failed to close {key}: {e}")

def execute(*sql, connection=None, script=None, sep='; ', args=None):
    """
    Thread-safe SQL execution.
    - SELECTs and other read queries run immediately (parallel safe).
    - DML/DDL statements (INSERT/UPDATE/DELETE/etc) are funneled into the write queue.
    - Multi-statement scripts are supported via executescript.
    - All write queue items are always 5-tuple: (sql, args, conn, result_q, is_script)
    """
    assert connection, "Pass connection= from gw.sql.open_connection()"

    if script:
        script_text = gw.resource(script, text=True)
        # Recursively call as a multi-statement script
        return execute(script_text, connection=connection)

    if sql:
        sql = sep.join(sql)
    else:
        raise ValueError("SQL statement required")

    # Detect if this is a multi-statement script (very basic: contains semicolon)
    # Note: More robust SQL parsing is possible but out of scope here.
    stripped_sql = sql.strip().rstrip(";")
    is_script = ";" in stripped_sql

    # If it is a read-only statement and not a script, execute directly
    if not _is_write_query(sql) and not is_script:
        cursor = connection.cursor()
        try:
            cursor.execute(sql, args or ())
            return cursor.fetchall() if cursor.description else None
        finally:
            cursor.close()
    else:
        # All writes or scripts are serialized via the queue.
        result_q = queue.Queue()
        # Always enqueue a 5-item tuple: (sql, args, conn, result_q, is_script)
        _write_queue.put((sql, args, connection._connection, result_q, is_script))
        rows, error = result_q.get()
        if error:
            raise error
        return rows


def _process_writes():
    while not _writer_shutdown.is_set():
        try:
            item = _write_queue.get(timeout=0.5)
        except queue.Empty:
            continue
        if item is None:
            _write_queue.task_done()
            break
        sql, args, conn, result_q, is_script = item  # Always expect 5!
        try:
            cursor = conn.cursor()
            if is_script:
                cursor.executescript(sql)
                rows = None
            elif args:
                cursor.execute(sql, args)
                rows = cursor.fetchall() if cursor.description else None
            else:
                cursor.execute(sql)
                rows = cursor.fetchall() if cursor.description else None
            conn.commit()
            result_q.put((rows, None))
        except Exception as e:
            conn.rollback()
            result_q.put((None, e))
        finally:
            cursor.close()
            _write_queue.task_done()


def _is_write_query(sql):
    sql = sql.strip().lower()
    # Simple heuristic: treat as write if it starts with DML or DDL
    return any(sql.startswith(word)
        for word in ("insert", "update", "delete", "create", "drop", "alter", "replace", "truncate", "vacuum", "attach", "detach"))


def _start_writer_thread():
    global _writer_thread
    if _writer_thread is None or not _writer_thread.is_alive():
        _writer_thread = threading.Thread(target=_process_writes, daemon=True)
        _writer_thread.start()


def shutdown_writer():
    """Signal writer thread to exit and wait for it to finish."""
    global _writer_thread
    _writer_shutdown.set()
    # Put enough poison pills for any possible writer threads (usually 1)
    _write_queue.put(None)
    if _writer_thread:
        _writer_thread.join(timeout=2)
        _writer_thread = None  # Allow restart
    # Clean up: clear shutdown flag for future tests
    _writer_shutdown.clear()
    # Drain any leftover queue items (to avoid memory leaks between tests)
    try:
        while True:
            _write_queue.get_nowait()
            _write_queue.task_done()
    except queue.Empty:
        pass
