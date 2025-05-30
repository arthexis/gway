import os
import csv
import sqlite3
from contextlib import contextmanager
from gway import gw


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


...


def infer_type(value):
    """Infer SQL type from a sample value."""
    try:
        float(value)
        return "REAL"
    except ValueError:
        return "TEXT"

