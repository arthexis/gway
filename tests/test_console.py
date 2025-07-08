# tests/test_console.py

import os
import tempfile
import unittest
from pathlib import Path

import gway.console as console


class TestChopFunction(unittest.TestCase):
    def test_chop_splits_on_dash_and_semicolon(self):
        self.assertEqual(
            console.chop(['a', 'b', '-', 'c', 'd']),
            [['a', 'b'], ['c', 'd']]
        )
        self.assertEqual(
            console.chop(['x', 'y', ';', 'z']),
            [['x', 'y'], ['z']]
        )

    def test_chop_handles_empty(self):
        self.assertEqual(console.chop([]), [])

    def test_chop_preserves_tokens(self):
        tokens = ['cmd', 'arg;with;semicolons', ';', 'next']
        self.assertEqual(
            console.chop(tokens),
            [['cmd', 'arg;with;semicolons'], ['next']]
        )


class TestNormalizeToken(unittest.TestCase):
    def test_normalize_replaces_delimiters_with_underscore(self):
        self.assertEqual(
            console.normalize_token('a-b.c d'),
            'a_b_c_d'
        )
        self.assertEqual(
            console.normalize_token('no-change'),
            'no_change'
        )


class TestLoadRecipeAbsolutePath(unittest.TestCase):
    def setUp(self):
        # Create a temporary recipe file with notes and indented options
        self.temp_file = tempfile.NamedTemporaryFile('w', delete=False)
        self.temp_file.write(
            """# comment1
cmd1 arg1 --opt1 val1
    --opt2 val2
# comment2

cmd2 --flag
"""
        )
        self.temp_file.close()

    def tearDown(self):
        os.remove(self.temp_file.name)

    def test_load_recipe_parses_commands_and_notes(self):
        commands, notes = console.load_recipe(self.temp_file.name)
        expected_notes = ['# comment1', '# comment2']
        expected_commands = [
            ['cmd1', 'arg1', '--opt1', 'val1'],
            ['cmd1', 'arg1', '--opt2', 'val2'],
            ['cmd2', '--flag']
        ]
        self.assertEqual(notes, expected_notes)
        self.assertEqual(commands, expected_commands)

    def test_load_recipe_nonexistent_raises_file_not_found(self):
        # Absolute nonexistent path should raise FileNotFoundError
        with self.assertRaises(FileNotFoundError):
            console.load_recipe(self.temp_file.name + '.doesnotexist')


class TestLoadRecipeRelativePath(unittest.TestCase):
    def setUp(self):
        # Create a fake recipes directory with a sample recipe (no extension and .gwr)
        self.temp_dir = tempfile.TemporaryDirectory()
        self.recipes_dir = Path(self.temp_dir.name) / 'recipes'
        self.recipes_dir.mkdir()
        content = (
            """# sample recipe
app start --port 8000
    --debug
"""
        )
        # Write without extension and with .gwr extension
        (self.recipes_dir / 'sample').write_text(content)
        (self.recipes_dir / 'sample.gwr').write_text(content)
        # Monkey-patch gw.resource to point to our fake recipes directory
        self.original_resource = console.gw.resource
        console.gw.resource = lambda category, name: str(self.recipes_dir / name)

    def tearDown(self):
        # Restore original resource resolver
        console.gw.resource = self.original_resource
        self.temp_dir.cleanup()

    def test_load_recipe_finds_gwr_extension(self):
        # Provide base name without extension
        commands, notes = console.load_recipe('sample')
        expected_commands = [
            ['app', 'start', '--port', '8000'],
            ['app', 'start', '--debug']
        ]
        expected_notes = ['# sample recipe']
        self.assertEqual(commands, expected_commands)
        self.assertEqual(notes, expected_notes)


class TestLoadRecipeColonSyntax(unittest.TestCase):
    def test_load_recipe_with_colon_repetition(self):
        content = (
            """web app make-app:
    --project one --home first
    --project two
web:
 - static collect
 - server serve-app --host 1 --port 2
"""
        )
        with tempfile.NamedTemporaryFile('w', delete=False) as f:
            f.write(content)
            temp_name = f.name
        try:
            commands, _ = console.load_recipe(temp_name)
        finally:
            os.remove(temp_name)

        expected = [
            ['web', 'app', 'make-app', '--project', 'one', '--home', 'first'],
            ['web', 'app', 'make-app', '--project', 'two'],
            ['web', 'static', 'collect'],
            ['web', 'server', 'serve-app', '--host', '1', '--port', '2'],
        ]
        self.assertEqual(commands, expected)

    def test_load_recipe_colon_without_indentation(self):
        content = (
            """web app make-app:
--project one
--project two
web:
- static collect
- server serve-app --host 1 --port 2
"""
        )
        with tempfile.NamedTemporaryFile('w', delete=False) as f:
            f.write(content)
            temp_name = f.name
        try:
            commands, _ = console.load_recipe(temp_name)
        finally:
            os.remove(temp_name)

        expected = [
            ['web', 'app', 'make-app', '--project', 'one'],
            ['web', 'app', 'make-app', '--project', 'two'],
            ['web', 'static', 'collect'],
            ['web', 'server', 'serve-app', '--host', '1', '--port', '2'],
        ]
        self.assertEqual(commands, expected)


if __name__ == '__main__':
    unittest.main()
