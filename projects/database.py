import sqlite3
import os
import csv


def connect(*, sql_engine="sqlite3", load_data=True):
    """Used by other functions to connect to the database. Returns a context manager.
        Data from the data folder is loaded into the database if load_data is True (default).
    """
    assert sql_engine == "sqlite3", "Only sqlite3 is supported at the moment."
    
    db_path = gsol.temp("gsol.sqlite")
    data_path = gsol.resource("data")
    conn = sqlite3.connect(db_path)

    def load_csv_to_db(path, parent_path=""):
        for item in os.listdir(path):
            full_path = os.path.join(path, item)
            if os.path.isdir(full_path):
                load_csv_to_db(full_path, parent_path=item if not parent_path else f"{parent_path}__{item}")
            elif item.endswith(".csv"):
                table_name = f"{parent_path}__{os.path.splitext(item)[0]}" if parent_path else os.path.splitext(item)[0]
                table_name = table_name.replace('-', '_')  # Replace hyphens with underscores for valid SQL names
                with open(full_path, 'r', encoding='utf-8') as csvfile:
                    reader = csv.reader(csvfile)
                    headers = next(reader)
                    
                    # Ensure unique column names
                    unique_headers = []
                    seen_headers = set()
                    for header in headers:
                        base_header = header
                        counter = 1
                        while header.lower() in seen_headers:
                            header = f"{base_header}_{counter}"
                            counter += 1
                        unique_headers.append(header)
                        seen_headers.add(header.lower())
                    
                    # Create table with unique column names
                    create_table_query = f"CREATE TABLE IF NOT EXISTS {table_name} ({', '.join(f'[{h}] TEXT' for h in unique_headers)})"
                    conn.execute(create_table_query)
                    
                    # Insert data
                    insert_query = f"INSERT INTO {table_name} ({', '.join(f'[{h}]' for h in unique_headers)}) VALUES ({', '.join('?' for _ in unique_headers)})"
                    conn.executemany(insert_query, reader)
                    conn.commit()
                    
                print(f"Loaded {table_name} with columns: {', '.join(unique_headers)}")

    class DatabaseConnection:
        def __init__(self, conn, db_path):
            self.conn = conn
            self.db_path = db_path
        
        def __repr__(self):
            return f"<{sql_engine} @ {self.db_path} ({data_path})>"
        
        def __enter__(self):
            return self.conn
    
        def __exit__(self, exc_type, exc_val, exc_tb):
            self.conn.close()

    if load_data:
        load_csv_to_db(data_path)
    return DatabaseConnection(conn, db_path)
