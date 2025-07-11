# tests/test_sql_crud.py

import unittest
import os
from gway import gw


class SqlCrudTests(unittest.TestCase):
    DB = "work/test_crud.sqlite"

    def setUp(self):
        path = gw.resource(self.DB)
        if os.path.exists(path):
            os.remove(path)
        with gw.sql.open_connection(self.DB) as cur:
            cur.execute('CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, qty INT)')

    def tearDown(self):
        gw.sql.close_connection(self.DB)
        path = gw.resource(self.DB)
        if os.path.exists(path):
            os.remove(path)

    def test_basic_crud_cycle(self):
        item_id = gw.sql.crud.api_create(table='items', name='apple', qty=5, dbfile=self.DB)
        row = gw.sql.crud.api_read(table='items', id=item_id, dbfile=self.DB)
        self.assertEqual(row[1], 'apple')
        gw.sql.crud.api_update(table='items', id=item_id, qty=10, dbfile=self.DB)
        row2 = gw.sql.crud.api_read(table='items', id=item_id, dbfile=self.DB)
        self.assertEqual(row2[2], 10)
        gw.sql.crud.api_delete(table='items', id=item_id, dbfile=self.DB)
        row3 = gw.sql.crud.api_read(table='items', id=item_id, dbfile=self.DB)
        self.assertIsNone(row3)

    def test_setup_table_adds_columns(self):
        gw.sql.crud.setup_table(
            table='extras',
            columns={'id': 'INTEGER PRIMARY KEY', 'name': 'TEXT'},
            dbfile=self.DB,
        )
        with gw.sql.open_connection(self.DB) as cur:
            cur.execute('PRAGMA table_info(extras)')
            cols = {r[1] for r in cur.fetchall()}
        self.assertIn('name', cols)

        gw.sql.crud.setup_table(
            table='extras',
            columns={'qty': 'INT'},
            dbfile=self.DB,
        )
        with gw.sql.open_connection(self.DB) as cur:
            cur.execute('PRAGMA table_info(extras)')
            cols2 = {r[1] for r in cur.fetchall()}
        self.assertIn('qty', cols2)


if __name__ == '__main__':
    unittest.main()
