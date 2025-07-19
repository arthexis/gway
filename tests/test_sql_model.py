import unittest
import os
from dataclasses import dataclass
from collections import namedtuple
from gway import gw

class SqlModelTests(unittest.TestCase):
    DB = "work/test_model.sqlite"
    DB_DUCK = "work/test_model.duckdb"

    def setUp(self):
        path = gw.resource(self.DB)
        if os.path.exists(path):
            os.remove(path)
        dpath = gw.resource(self.DB_DUCK)
        if os.path.exists(dpath):
            os.remove(dpath)

    def tearDown(self):
        gw.sql.close_connection(self.DB)
        gw.sql.close_connection(self.DB_DUCK, sql_engine="duckdb")
        path = gw.resource(self.DB)
        if os.path.exists(path):
            os.remove(path)
        dpath = gw.resource(self.DB_DUCK)
        if os.path.exists(dpath):
            os.remove(dpath)

    def test_dataclass_model(self):
        @dataclass
        class Note:
            id: int
            text: str

        notes = gw.sql.model(Note, dbfile=self.DB)
        nid = notes.create(text="hi")
        row = notes.read(nid)
        self.assertEqual(row[1], "hi")

    def test_mapping_model(self):
        spec = {"__name__": "things", "id": "INTEGER PRIMARY KEY AUTOINCREMENT", "foo": "TEXT"}
        things = gw.sql.model(spec, dbfile=self.DB)
        tid = things.create(foo="bar")
        row = things.read(tid)
        self.assertEqual(row[1], "bar")

    def test_namedtuple_model(self):
        Pet = namedtuple("Pet", "id name")
        pets = gw.sql.model("pets (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT)", dbfile=self.DB)
        pid = pets.create(name="bob")
        row = pets.read(pid)
        self.assertEqual(row[1], "bob")

    def test_duckdb_model(self):
        spec = {"__name__": "items", "id": "INTEGER", "name": "TEXT"}
        items = gw.sql.model(spec, dbfile=self.DB_DUCK, sql_engine="duckdb")
        items.create(id=1, name="foo")
        row = items.read(1, id_col="id")
        self.assertEqual(row[1], "foo")

    def test_context_defaults(self):
        global DBFILE
        DBFILE = self.DB
        spec = {"__name__": "notes_auto", "id": "INTEGER PRIMARY KEY AUTOINCREMENT", "text": "TEXT"}
        notes = gw.sql.model(spec)
        nid = notes.create(text="auto")
        row = notes.read(nid)
        self.assertEqual(row[1], "auto")
        gw.sql.close_connection(DBFILE)
        del globals()["DBFILE"]

if __name__ == "__main__":
    unittest.main()
