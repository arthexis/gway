import os
import csv
import sqlite3
import logging

from gway import Gateway

logger = logging.getLogger(__name__)


def connect(*, sql_engine="sqlite3", load_data=True):
    """Used by other functions to connect to the database. Returns a context manager.
        Data from the data folder is loaded into the database if load_data is True (default).
    """
    assert sql_engine == "sqlite3", "Only sqlite3 is supported at the moment."
    gway = Gateway()
    
    db_path = gway.resource("temp", "gsol.sqlite")
    data_path = os.path.join(gway.root, "data")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    def load_csv_to_db(path, parent_path=""):
        for item in os.listdir(path):
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                # Recurse into subdirectory, update parent path
                new_parent = item if not parent_path else f"{parent_path}_{item}"
                load_csv_to_db(full_path, new_parent)
            elif item.endswith(".csv"):
                # Build table name including parent path
                base_name = os.path.splitext(item)[0]
                table_name = f"{parent_path}_{base_name}" if parent_path else base_name
                table_name = table_name.replace('-', '_')  # Make it SQL-safe
                with open(full_path, 'r', encoding='utf-8') as csvfile:
                    reader = csv.reader(csvfile)
                    try:
                        headers = next(reader)
                    except StopIteration:
                        logger.warning(f"Skipping empty CSV file: {full_path}")
                        continue
                    
                    # Ensure unique column names
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
                    
                    # Create table with unique column names
                    create_table_query = (f"CREATE TABLE IF NOT EXISTS [{table_name}] "
                                          f"({', '.join(f'[{h}] TEXT' for h in unique_headers)})")
                    cursor.execute(create_table_query)
                    
                    # Insert data
                    insert_query = (f"INSERT INTO [{table_name}] ({', '.join(f'[{h}]' for h in unique_headers)}) "
                                    f"VALUES ({', '.join('?' for _ in unique_headers)})")
                    cursor.executemany(insert_query, reader)
                    
                logger.info(f"Loaded table '{table_name}' with columns: {', '.join(unique_headers)}")

    if load_data:
        load_csv_to_db(data_path)

    return cursor
