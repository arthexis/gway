# tests/test_console.py

import os
import sys
import tempfile
import unittest
import types
from pathlib import Path
from unittest.mock import patch

import gway.console as console


def _extract_tokens(chunks):
    return [chunk["tokens"] for chunk in chunks if chunk.get("tokens")]


class TestChunkFunction(unittest.TestCase):
    def test_chunk_splits_on_dash_and_semicolon(self):
        self.assertEqual(
            console.chunk(['a', 'b', '-', 'c', 'd']),
            [['a', 'b'], ['c', 'd']]
        )
        self.assertEqual(
            console.chunk(['x', 'y', ';', 'z']),
            [['x', 'y'], ['z']]
        )

    def test_chunk_handles_empty(self):
        self.assertEqual(console.chunk([]), [])

    def test_chunk_preserves_tokens(self):
        tokens = ['cmd', 'arg;with;semicolons', ';', 'next']
        self.assertEqual(
            console.chunk(tokens),
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
        # Create a temporary recipe file with comments and indented options
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

    def test_load_recipe_parses_commands_and_comments(self):
        commands, comments = console.load_recipe(self.temp_file.name)
        expected_comments = ['# comment1', '# comment2']
        expected_commands = [
            ['cmd1', 'arg1', '--opt1', 'val1'],
            ['cmd1', 'arg1', '--opt2', 'val2'],
            ['cmd2', '--flag']
        ]
        self.assertEqual(comments, expected_comments)
        self.assertEqual(_extract_tokens(commands), expected_commands)

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
        (self.recipes_dir / 'sample_script.gwr').write_text('cmd hyphen')
        # Monkey-patch gw.resource to point to our fake recipes directory
        self.original_resource = console.gw.resource
        console.gw.resource = lambda category, name: str(self.recipes_dir / name)

    def tearDown(self):
        # Restore original resource resolver
        console.gw.resource = self.original_resource
        self.temp_dir.cleanup()

    def test_load_recipe_finds_gwr_extension(self):
        # Provide base name without extension
        commands, comments = console.load_recipe('sample')
        expected_commands = [
            ['app', 'start', '--port', '8000'],
            ['app', 'start', '--debug']
        ]
        expected_comments = ['# sample recipe']
        self.assertEqual(_extract_tokens(commands), expected_commands)
        self.assertEqual(comments, expected_comments)

    def test_load_recipe_accepts_dotted_name(self):
        # File exists as arthexis_com.gwr but load with dot
        (self.recipes_dir / 'arthexis_com.gwr').write_text('cmd run')
        commands, _ = console.load_recipe('arthexis.com')
        self.assertEqual(_extract_tokens(commands), [['cmd', 'run']])

    def test_load_recipe_accepts_dotted_path(self):
        (self.recipes_dir / 'foo').mkdir()
        (self.recipes_dir / 'foo' / 'bar.gwr').write_text('cmd go')
        commands, _ = console.load_recipe('foo.bar')
        self.assertEqual(_extract_tokens(commands), [['cmd', 'go']])

    def test_load_recipe_accepts_hyphenated_name(self):
        commands, _ = console.load_recipe('sample-script')
        self.assertEqual(_extract_tokens(commands), [['cmd', 'hyphen']])


class TestLoadRecipeColonSyntax(unittest.TestCase):
    def test_load_recipe_with_colon_repetition(self):
        content = (
            """dummy app setup-app:
    - one --home first
    - two
dummy:
 - static collect
 - server start-app --host 1 --port 2
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
            ['dummy', 'app', 'setup-app', 'one', '--home', 'first'],
            ['dummy', 'app', 'setup-app', 'two'],
            ['dummy', 'static', 'collect'],
            ['dummy', 'server', 'start-app', '--host', '1', '--port', '2'],
        ]
        self.assertEqual(_extract_tokens(commands), expected)

    def test_load_recipe_colon_without_indentation(self):
        content = (
            """dummy app setup-app:
    - one
    - two
dummy:
- static collect
- server start-app --host 1 --port 2
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
            ['dummy', 'app', 'setup-app', 'one'],
            ['dummy', 'app', 'setup-app', 'two'],
            ['dummy', 'static', 'collect'],
            ['dummy', 'server', 'start-app', '--host', '1', '--port', '2'],
        ]
        self.assertEqual(_extract_tokens(commands), expected)

    def test_load_recipe_colon_after_flag_mid_line(self):
        content = (
            """dummy server start-app --port: --ws-port 9999
    - 8888
    - 7777
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
            ['dummy', 'server', 'start-app', '--port', '8888', '--ws-port', '9999'],
            ['dummy', 'server', 'start-app', '--port', '7777', '--ws-port', '9999'],
        ]
        self.assertEqual(_extract_tokens(commands), expected)

    def test_load_recipe_backslash_continuation(self):
        content = (
            """cmd --one 1 \\
    --two 2
"""
        )
        with tempfile.NamedTemporaryFile('w', delete=False) as f:
            f.write(content)
            temp_name = f.name
        try:
            commands, _ = console.load_recipe(temp_name)
        finally:
            os.remove(temp_name)

        expected = [[
            'cmd', '--one', '1', '--two', '2'
        ]]
        self.assertEqual(_extract_tokens(commands), expected)


class TestLoadRecipeSections(unittest.TestCase):
    def test_section_filters_commands_and_includes_prelude(self):
        content = (
            """prep run\n# Section One\nfirst do\n## Details\nsecond step\n# Section Two\nthird step\n"""
        )
        with tempfile.NamedTemporaryFile('w', delete=False) as handle:
            handle.write(content)
            recipe_path = handle.name
        try:
            commands, comments = console.load_recipe(recipe_path, section="# section one")
        finally:
            os.remove(recipe_path)

        tokens = _extract_tokens(commands)
        self.assertEqual(tokens, [["prep", "run"], ["first", "do"], ["second", "step"]])
        chunk_comments = [chunk.get("comment") for chunk in commands if chunk.get("comment")]
        self.assertIn('# Section One', chunk_comments)
        self.assertIn('## Details', chunk_comments)
        self.assertNotIn('# Section Two', chunk_comments)

    def test_missing_section_raises_value_error(self):
        with tempfile.NamedTemporaryFile('w', delete=False) as handle:
            handle.write("cmd one\n# Another\ncmd two\n")
            recipe_path = handle.name
        try:
            with self.assertRaises(ValueError):
                console.load_recipe(recipe_path, section="# missing")
        finally:
            os.remove(recipe_path)


class TestPrepareKwargParsing(unittest.TestCase):
    def test_multi_word_kwargs(self):
        import argparse

        def dummy(**kwargs):
            return kwargs

        dummy.__var_keyword_name__ = "kwargs"

        parsed = argparse.Namespace(kwargs=[
            "--title", "My", "Great", "App", "--flag", "on"
        ])

        args, kw = console.prepare(parsed, dummy)

        self.assertEqual(args, [])
        self.assertEqual(kw["title"], "My Great App")
        self.assertEqual(kw["flag"], "on")

    def test_unquoted_known_option(self):
        import argparse

        def dummy(*, title=""):
            return title

        parser = argparse.ArgumentParser()
        console.add_func_args(parser, dummy)
        tokens = console.join_unquoted_kwargs(["--title", "My", "Great", "App"])
        parsed = parser.parse_args(tokens)
        args, kw = console.prepare(parsed, dummy)

        self.assertEqual(args, [])
        self.assertEqual(kw["title"], "My Great App")

    def test_optional_positional_precedes_varargs(self):
        import argparse

        def dummy(recipe=None, *recipe_args):
            return recipe, recipe_args

        parser = argparse.ArgumentParser()
        console.add_func_args(parser, dummy)

        parsed, unknown = parser.parse_known_args(["auto-upgrade", "--latest"])
        extra = list(getattr(parsed, "recipe_args", []) or [])
        extra.extend(unknown)
        setattr(parsed, "recipe_args", extra)

        args, kw = console.prepare(parsed, dummy)

        self.assertEqual(args, ["auto-upgrade", "--latest"])
        self.assertNotIn("recipe", kw)


class TestUnionAnnotations(unittest.TestCase):
    def test_add_func_args_handles_pep604_optional(self):
        import argparse

        def dummy(*, count: int | None = None):
            return count

        parser = argparse.ArgumentParser()
        console.add_func_args(parser, dummy)

        parsed = parser.parse_args([])
        self.assertIsNone(parsed.count)

        parsed = parser.parse_args(["--count", "5"])
        self.assertEqual(parsed.count, 5)


class TestRecipeCliContext(unittest.TestCase):
    def test_extra_cli_args_as_context(self):
        fake_commands = [['noop']]
        original_argv = sys.argv

        class DummyGateway:
            def __init__(self, **kwargs):
                pass

            def verbose(self, *args, **kwargs):
                pass

        try:
            with patch('gway.console.argcomplete.autocomplete', lambda *a, **k: None), \
                 patch('gway.console.load_recipe', return_value=(fake_commands, [])), \
                 patch('gway.console.process') as mock_process, \
                 patch('gway.console.setup_logging', lambda *a, **k: None), \
                 patch('gway.console.Gateway', DummyGateway):
                mock_process.return_value = ([], None)
                sys.argv = ['gway', '-r', 'dummy.gwr', '--foo', 'bar', '--flag']
                console.cli_main()
                kwargs = mock_process.call_args.kwargs
                self.assertEqual(kwargs['foo'], 'bar')
                self.assertTrue(kwargs['flag'])
        finally:
            sys.argv = original_argv

    def test_multiple_recipes_execute_in_parallel(self):
        original_argv = sys.argv

        class DummyGateway:
            def __init__(self, **kwargs):
                pass

            def verbose(self, *args, **kwargs):
                pass

        calls = []

        def fake_load(recipe_name, *, strict=True, section=None):
            return [[recipe_name]], []

        def fake_process(commands, **kwargs):
            recipe_name = commands[0][0]
            calls.append(recipe_name)
            return ([f"{recipe_name}-result"], f"{recipe_name}-last")

        try:
            with patch('gway.console.argcomplete.autocomplete', lambda *a, **k: None), \
                 patch('gway.console.load_recipe', side_effect=fake_load), \
                 patch('gway.console.process') as mock_process, \
                 patch('gway.console.setup_logging', lambda *a, **k: None), \
                 patch('gway.console.Gateway', DummyGateway), \
                 patch('builtins.print') as mock_print:
                mock_process.side_effect = fake_process
                sys.argv = ['gway', '-r', 'first', 'second']
                console.cli_main()
                self.assertEqual(mock_process.call_count, 2)
                self.assertEqual(set(calls), {'first', 'second'})
                self.assertEqual(mock_print.call_args_list[-1].args[0], 'second-last')
        finally:
            sys.argv = original_argv

    def test_context_only_arguments_report_nothing_to_do(self):
        original_argv = sys.argv

        class DummyGateway:
            def __init__(self, **kwargs):
                pass

            def verbose(self, *args, **kwargs):
                pass

        try:
            with patch('gway.console.argcomplete.autocomplete', lambda *a, **k: None), \
                 patch('gway.console.setup_logging', lambda *a, **k: None), \
                 patch('gway.console.Gateway', DummyGateway), \
                 patch('gway.console.process') as mock_process, \
                 patch('builtins.print') as mock_print:
                sys.argv = ['gway', '--upgrade']
                console.cli_main()
                mock_process.assert_not_called()
                messages = [call.args[0] for call in mock_print.call_args_list]
                self.assertIn('Nothing to do. -> --upgrade', messages)
        finally:
            sys.argv = original_argv

    def test_context_only_arguments_with_values_supported(self):
        original_argv = sys.argv

        class DummyGateway:
            def __init__(self, **kwargs):
                pass

            def verbose(self, *args, **kwargs):
                pass

        try:
            with patch('gway.console.argcomplete.autocomplete', lambda *a, **k: None), \
                 patch('gway.console.setup_logging', lambda *a, **k: None), \
                 patch('gway.console.Gateway', DummyGateway), \
                 patch('gway.console.process') as mock_process, \
                 patch('builtins.print') as mock_print:
                sys.argv = ['gway', '--tag', 'alpha']
                console.cli_main()
                mock_process.assert_not_called()
                messages = [call.args[0] for call in mock_print.call_args_list]
                self.assertIn('Nothing to do. -> --tag=alpha', messages)
        finally:
            sys.argv = original_argv

    def test_leaked_argcomplete_marker_does_not_exit_early(self):
        original_argv = sys.argv

        class DummyGateway:
            def __init__(self, **kwargs):
                pass

            def verbose(self, *args, **kwargs):
                pass

        try:
            sys.argv = ['gway']
            with patch.dict(os.environ, {'_ARGCOMPLETE': '1'}, clear=False), \
                 patch('gway.console.setup_logging', lambda *a, **k: None), \
                 patch('gway.console.Gateway', DummyGateway), \
                 patch.object(console.argparse.ArgumentParser, 'print_help') as mock_help, \
                 patch('gway.console.argcomplete.autocomplete') as mock_autocomplete:
                with self.assertRaises(SystemExit):
                    console.cli_main()
            mock_autocomplete.assert_not_called()
            mock_help.assert_called_once()
        finally:
            sys.argv = original_argv


class TestProcessChaining(unittest.TestCase):
    def test_reuses_project_for_chained_calls(self):
        commands = [["dummy", "setup-home"], ["setup-links"]]
        results, last = console.process(commands)
        self.assertEqual(results[0], "index")
        self.assertEqual(results[1], ["about", "more"])
        self.assertEqual(last, ["about", "more"])

    def test_chained_auto_injection(self):
        from gway.gateway import Gateway

        dummy = Gateway()

        def record():
            return "foo.wav"

        record.__module__ = "projects.audio"

        def playback(*, audio):
            return audio

        playback.__module__ = "projects.audio"

        dummy.audio = types.SimpleNamespace(
            record=dummy.wrap_callable("audio.record", record),
            playback=dummy.wrap_callable("audio.playback", playback),
        )

        commands = [["audio", "record"], ["playback"]]
        with patch("gway.gw", dummy), patch("gway.console.gw", dummy):
            results, last = console.process(commands)

        self.assertEqual(results[0], "foo.wav")
        self.assertEqual(results[1], "foo.wav")
        self.assertEqual(last, "foo.wav")


class TestRecipeComments(unittest.TestCase):
    def setUp(self):
        console.gw.context.clear()

    def tearDown(self):
        console.gw.context.clear()

    def test_process_prints_comments_with_sigils(self):
        console.gw.context['NAME'] = 'Agent'
        commands = [
            {"tokens": [], "comment": "# Prelude [NAME]", "section": None},
            {"tokens": ["dummy", "setup-home"], "comment": "# Running for [NAME]", "section": None},
        ]
        with patch('builtins.print') as mock_print:
            console.process(commands, origin="recipe")

        printed = [call.args[0] for call in mock_print.call_args_list]
        self.assertIn('# Prelude Agent', printed)
        self.assertIn('# Running for Agent', printed)


class TestProcessRecipeFallback(unittest.TestCase):
    def test_process_invokes_recipe_when_command_missing(self):
        commands = [["missing-recipe"]]

        with tempfile.TemporaryDirectory() as temp_dir:
            recipes_dir = Path(temp_dir) / "recipes"
            recipes_dir.mkdir()
            (recipes_dir / "missing-recipe.gwr").write_text("dummy setup-home")

            original_resource = console.gw.resource

            def fake_resource(*parts):
                if parts and parts[0] == "recipes":
                    return str(Path(recipes_dir, *parts[1:]))
                return original_resource(*parts)

            console.gw.resource = fake_resource
            try:
                results, last = console.process(commands)
            finally:
                console.gw.resource = original_resource

        self.assertEqual(results, ["index"])
        self.assertEqual(last, "index")


class TestProcessSigilResolution(unittest.TestCase):
    def setUp(self):
        console.gw.context.clear()
        console.gw.results.clear()

    def test_process_resolves_sigils(self):
        console.gw.context['P'] = 'val'
        cmds = [['hello-world', '[P]']]
        _, last = console.process(cmds)
        self.assertEqual(last['name'], 'val')


class TestRepeatBuiltin(unittest.TestCase):
    def test_repeat_replays_previous_commands(self):
        commands = [["hello-world", "Agent"], ["repeat", "--times", "2", "--rest", "0"]]
        results, last = console.process(commands)

        self.assertEqual(len(results), 3)
        self.assertTrue(all(result["name"] == "Agent" for result in results))
        self.assertEqual(last["name"], "Agent")

    def test_repeat_in_recipe_replays_all_steps(self):
        commands = [
            ["hello-world", "Alpha"],
            ["hello-world", "Beta"],
            ["repeat", "--times", "1", "--rest", "0"],
        ]
        results, last = console.process(commands, origin="recipe")

        self.assertEqual([r["name"] for r in results], ["Alpha", "Beta", "Alpha", "Beta"])
        self.assertEqual(last["name"], "Beta")

    def test_repeat_requires_previous_commands(self):
        with self.assertRaises(SystemExit):
            console.process([["repeat", "--times", "1", "--rest", "0"]])


if __name__ == '__main__':
    unittest.main()
