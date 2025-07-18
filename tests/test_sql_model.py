import unittest
import os
from dataclasses import dataclass
from collections import namedtuple
from gway import gw

class SqlModelTests(unittest.TestCase):
    DB = "work/test_model.sqlite"

    def setUp(self):
        path = gw.resource(self.DB)
        if os.path.exists(path):
            os.remove(path)

    def tearDown(self):
        gw.sql.close_connection(self.DB)
        path = gw.resource(self.DB)
        if os.path.exists(path):
            os.remove(path)

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

if __name__ == "__main__":
    unittest.main()
