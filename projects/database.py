import os
import csv
import sqlite3
from contextlib import contextmanager
from gway import gw


def infer_type(value):
    """Infer SQL type from a sample value."""
    try:
        float(value)
        return "REAL"
    except ValueError:
        return "TEXT"
    
    
@contextmanager
def connect(
        *database, sql_engine="sqlite3", load_data=False, force=False, 
        temp_name="local.sqlite", row_factory=False, 
    ):
    """
    Connects to a SQLite database using a context manager.
    Loads CSV data from the data folder if load_data is True.
    If force is True, existing tables are dropped and reloaded.
    """
    assert sql_engine == "sqlite3", "Only sqlite3 is supported at the moment."

    if not database:
        database = ("temp", temp_name)

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
                        infer_type(sample_row[i]) if i < len(sample_row) else "TEXT"
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


def table(
    name,
    *database,
    sql_engine="sqlite3",
    load_data=False,
    force=False,
    temp_name="local.sqlite",
    row_factory=False,
    select=None,
    limit=None,
    where=None,
    **filters
):
    """
    Fetch rows from `name` in a SQLite DB.

    Parameters:
      name (str): name of the table to query.
      *database, sql_engine, temp_name, force, row_factory: passed through to `connect()`.
      load_data (bool): if True, CSV data for only this table is loaded.
      select (str | list[str]): columns to project; defaults to '*'.
      where (str): raw SQL fragment for additional filtering.
      limit (int): maximum number of rows to return.
      **filters: column=value pairs to build WHERE clauses. If value is a string
                 starting with '>=', '<=', '>', or '<', that operator is used.

    Returns:
      list of rows (tuples or sqlite3.Row if row_factory=True).
    """
    # when loading data, restrict to this table’s CSV directory
    load_arg = name if load_data else False

    with connect(
        *database,
        sql_engine=sql_engine,
        load_data=load_arg,
        force=force,
        temp_name=temp_name,
        row_factory=row_factory
    ) as cursor:
        # build SELECT clause
        if select:
            if isinstance(select, (list, tuple)):
                select_clause = ", ".join(select)
            else:
                select_clause = str(select)
        else:
            select_clause = "*"

        # build WHERE clauses from filters
        conditions = []
        params = []
        for col, val in filters.items():
            op = "="
            operand = val
            if isinstance(val, str):
                for prefix in (">=", "<=", ">", "<"):
                    if val.startswith(prefix):
                        op = prefix
                        operand = val[len(prefix):]
                        break
            conditions.append(f"[{col}] {op} ?")
            params.append(operand)

        # include raw WHERE if provided
        if where:
            conditions.append(f"({where})")

        where_clause = ""
        if conditions:
            where_clause = " WHERE " + " AND ".join(conditions)

        # assemble LIMIT
        limit_clause = f" LIMIT {int(limit)}" if limit is not None else ""

        sql = f"SELECT {select_clause} FROM [{name}]{where_clause}{limit_clause}"
        cursor.execute(sql, params)
        return cursor.fetchall()
