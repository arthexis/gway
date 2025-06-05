import os
import csv
import sqlite3
from contextlib import contextmanager
from gway import gw


@contextmanager
def connect(
        *database, sql_engine="sqlite3", load_data=False, force=False, 
        work_db="local.sqlite", root="work", row_factory=False, 
    ):
    """
    Connects to a SQLite database using a context manager.
    Loads CSV data from the data folder if load_data is True.
    If force is True, existing tables are dropped and reloaded.
    """
    assert sql_engine == "sqlite3", "Only sqlite3 is supported at the moment."

    if not database: database = (root, work_db)

    db_path = gw.resource(*database)
    if isinstance(load_data, str):
        data_path = gw.resource("data", load_data)
        initial_parent = os.path.basename(load_data.rstrip("/\\"))
    else:
        data_path = gw.resource("data")
        initial_parent = ""

    conn = sqlite3.connect(db_path)

    def load_csv(path, parent_path=""):
        cursor = conn.cursor()
        for item in os.listdir(path):
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                new_parent = item if not parent_path else f"{parent_path}_{item}"
                load_csv(full_path, new_parent)
            elif item.endswith(".csv"):
                base_name = os.path.splitext(item)[0]
                name = f"{parent_path}_{base_name}" if parent_path else base_name
                name = name.replace('-', '_')  # Make SQL-safe

                with open(full_path, 'r', encoding='utf-8') as csvfile:
                    reader = csv.reader(csvfile)
                    try:
                        headers = next(reader)
                        sample_row = next(reader)
                    except StopIteration:
                        gw.warning(f"Skipping empty CSV file: {full_path}")
                        continue

                    unique_headers = []
                    seen_headers = set()
                    for header in headers:
                        base_header = header.strip()
                        header = base_header
                        counter = 1
                        while header.lower() in seen_headers:
                            header = f"{base_header}_{counter}"
                            counter += 1
                        unique_headers.append(header)
                        seen_headers.add(header.lower())

                    column_types = [
                        _infer_type(sample_row[i]) if i < len(sample_row) else "TEXT"
                        for i in range(len(unique_headers))
                    ]

                    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,))
                    table_exists = cursor.fetchone()

                    if table_exists and force:
                        cursor.execute(f"DROP TABLE IF EXISTS [{name}]")
                        gw.info(f"Dropped existing table '{name}' due to force=True")

                    if not table_exists or force:
                        create_table_query = (f"CREATE TABLE [{name}] (" 
                                              f"{', '.join(f'[{unique_headers[i]}] {column_types[i]}' for i in range(len(unique_headers)))})")
                        cursor.execute(create_table_query)
                        insert_query = (f"INSERT INTO [{name}] ({', '.join(f'[{h}]' for h in unique_headers)}) "
                                        f"VALUES ({', '.join('?' for _ in unique_headers)})")

                        cursor.execute(insert_query, sample_row)
                        cursor.executemany(insert_query, reader)
                        cursor.execute("COMMIT")
                        gw.info(f"Loaded table '{name}' with columns: {', '.join(unique_headers)}")
                    else:
                        gw.info(f"Skipped existing table '{name}' (force=False)")
        cursor.close()

    if load_data:
        load_csv(data_path, parent_path=initial_parent)
    
    if callable(row_factory):
        conn.row_factory = row_factory
    elif row_factory:
        conn.row_factory = sqlite3.Row

    cursor = conn.cursor()
    yield cursor
    conn.close()


def query(*queries, limit=None, **kwargs):
    """
    Execute a SQL query or script on the work/local.sqlite database by default.
    Different kwargs can be passed to sql.connect by prefixing them with _.
    Otherwise, kwargs can be used to add filters to the query.
    """
    filters = {k: v for k, v in kwargs.items() if not k.startswith("_")}
    connect_kwargs = {k: v for k, v in kwargs.items() if k.startswith("_")}
    connect_kwargs = {k[1:]: v for k, v in connect_kwargs.items()}

    with connect(**connect_kwargs) as conn:
        if len(queries) == 1:
            q = queries[0]
            if isinstance(q, str) and q.endswith(".sql"):
                sql_path = gw.resource("sql", q)
                with open(sql_path, "r", encoding="utf-8") as f:
                    sql = f.read()
            elif isinstance(q, str) and _is_sql_snippet(q):
                sql = q
            else:
                tables = [q]
        else:
            tables = list(queries)

        if 'tables' in locals():
            sql = f"SELECT * FROM {' NATURAL JOIN '.join(f'[{t}]' for t in tables)}"
            if filters:
                clauses = [f"[{k}] = ?" for k in filters]
                sql += f" WHERE {' AND '.join(clauses)}"
            if limit is not None:
                sql += f" LIMIT {int(limit)}"
            values = list(filters.values())
        else:
            values = []

        cursor = conn
        cursor.execute(sql, values)
        rows = cursor.fetchall()
        if hasattr(cursor, "description") and cursor.description:
            columns = [col[0] for col in cursor.description]
            return [dict(zip(columns, row)) for row in rows]
        return rows


_version = None


def record(*dest, **cols):
    global _version
    _version = _version or gw.version()

    *conn_path, table = dest
    connect_kwargs = {k[1:]: v for k, v in cols.items() if k.startswith("_")}
    data_cols = {k: v for k, v in cols.items() if not k.startswith("_")}

    full_cols = {
        **data_cols,
        "created_on": gw.now(),
        "gway_version": _version,
        "gway_uuid": gw.uuid(),
    }

    with connect(*conn_path, **connect_kwargs) as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        table_exists = cursor.fetchone()

        if table_exists:
            cursor.execute(f"PRAGMA table_info([{table}])")
            existing_cols = [row[1] for row in cursor.fetchall()]
            if not all(col in existing_cols for col in full_cols):
                backup = f"{table}_bak"
                cursor.execute(f"ALTER TABLE [{table}] RENAME TO [{backup}]")
                col_defs = ', '.join(f"[{k}] {_infer_type(v)}" for k, v in full_cols.items())
                cursor.execute(f"CREATE TABLE [{table}] ({col_defs})")
                shared = [col for col in existing_cols if col in full_cols]
                if shared:
                    cols_str = ', '.join(f"[{col}]" for col in shared)
                    cursor.execute(f"INSERT INTO [{table}] ({cols_str}) SELECT {cols_str} FROM [{backup}]")
                cursor.execute(f"DROP TABLE [{backup}]")
        else:
            col_defs = ', '.join(f"[{k}] {_infer_type(v)}" for k, v in full_cols.items())
            cursor.execute(f"CREATE TABLE [{table}] ({col_defs})")

        keys = list(full_cols)
        values = list(full_cols.values())
        placeholders = ', '.join('?' for _ in keys)
        cursor.execute(
            f"INSERT INTO [{table}] ({', '.join(f'[{k}]' for k in keys)}) VALUES ({placeholders})", 
            values
        )
        cursor.connection.commit()


def load(*dest, source=None, _headers=None, **opts):
    """
    Bulk load data into a database table.
    Accepts:
    - source= a list of dicts
    - source= a list of lists or tuples with _headers specified
    - source= a CSV/TSV/CDV file
    - source= a SQL query (str) to evaluate via `query()`
    """
    assert source is not None, "Must provide `source` with a valid source"
    *conn_path, table = dest

    # Determine the data
    if isinstance(source, str):
        if source.endswith(".sql"):
            rows = query(source, **opts)
        elif source.endswith(".tsv"):
            sep = "\t"
            with open(source, "r", encoding="utf-8") as f:
                reader = csv.reader(f, delimiter=sep)
                headers = next(reader)
                rows = [dict(zip(headers, row)) for row in reader]
        elif source.endswith(".cdv"):
            sep = ":"
            with open(source, "r", encoding="utf-8") as f:
                reader = csv.reader(f, delimiter=sep)
                headers = next(reader)
                rows = [dict(zip(headers, row)) for row in reader]
        elif source.endswith(".csv"):
            with open(source, "r", encoding="utf-8") as f:
                reader = csv.reader(f)
                headers = next(reader)
                rows = [dict(zip(headers, row)) for row in reader]
        else:
            raise ValueError(f"Unrecognized file format for '{source}'")
    elif isinstance(source, list):
        if all(isinstance(row, dict) for row in source):
            rows = source
        elif all(isinstance(row, (list, tuple)) for row in source):
            assert _headers, "Must provide _headers when using list-of-lists"
            rows = [dict(zip(_headers, row)) for row in source]
        else:
            raise TypeError("List must contain dicts or tuples/lists")
    else:
        raise TypeError(f"Unsupported type for source: {type(source)}")

    if not rows:
        gw.warning(f"No data to load into table '{table}'")
        return

    # Insert into database
    with connect(*conn_path, **opts) as cursor:
        columns = list(rows[0])
        col_defs = ', '.join(f"[{col}] {_infer_type(rows[0][col])}" for col in columns)

        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        exists = cursor.fetchone()
        if not exists:
            cursor.execute(f"CREATE TABLE [{table}] ({col_defs})")

        placeholders = ', '.join('?' for _ in columns)
        insert_sql = f"INSERT INTO [{table}] ({', '.join(f'[{col}]' for col in columns)}) VALUES ({placeholders})"
        values = [tuple(row[col] for col in columns) for row in rows]
        cursor.executemany(insert_sql, values)
        cursor.connection.commit()


def _is_sql_snippet(text):
    return any(word in text.lower() for word in ["select", "insert", "update", "delete"])


def _infer_type(value):
    """Infer SQL type from a sample value."""
    try:
        float(value)
        return "REAL"
    except ValueError:
        return "TEXT"

# TODO: Use the sql project to implement a simple credit/debit account system
# 