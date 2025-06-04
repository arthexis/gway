# gway/builtins.py

import os
import ast
import pathlib
import inspect
from collections.abc import Iterable
from types import FunctionType
from typing import Any, Callable, List, Optional, Type


# Avoid importing Gateway at the top level in this file specifically (circular import)
# Instead, use "from gway import gw" inside the function definitions themselves
    

def hello_world(name: str = "World", *, greeting: str = "Hello"):
    """Smoke test function."""
    from gway import gw

    message = f"{greeting.title()}, {name.title()}!"
    if hasattr(gw, "hello_world"): print(message)
    else: print("Greeting protocol not found ((serious smoke)).")
    return locals()


def abort(message: str, *, exit_code: int = 1) -> int:
    """Abort with error message."""
    from gway import gw

    gw.critical(message)
    print(f"Halting: {message}")
    raise SystemExit(exit_code)


def envs(filter: str = None) -> dict:
    """Return all environment variables in a dictionary."""
    if filter:
        filter = filter.upper()
        return {k: v for k, v in os.environ.items() if filter in k}
    else: 
        return os.environ.copy()


def version(check=None) -> str:
    """Return the version of the package. If `check` is provided,
    ensure the version meets or exceeds the required `major.minor.patch` string.
    Raise AssertionError if requirement is not met.
    """
    from gway import gw

    def parse_version(vstr):
        parts = vstr.strip().split(".")
        if len(parts) == 1:
            parts = (parts[0], '0', '0')
        elif len(parts) == 2:
            parts = (parts[0], parts[1], '0')
        if len(parts) > 3:
            raise ValueError(f"Invalid version format: '{vstr}', expected 'major.minor.patch'")
        return tuple(int(part) for part in parts)

    # Get the version in the VERSION file
    version_path = gw.resource("VERSION")
    if os.path.exists(version_path):
        with open(version_path, "r") as version_file:
            current_version = version_file.read().strip()

        if check:
            current_tuple = parse_version(current_version)
            required_tuple = parse_version(check)
            if current_tuple < required_tuple:
                raise AssertionError(f"Required version >= {check}, found {current_version}")

        return current_version
    else:
        gw.critical("VERSION file not found.")
        return "unknown"


def resource(*parts, touch=False, check=False):
    """
    Construct a path relative to the base, or the Gateway root if not specified.
    Assumes last part is a file and creates parent directories along the way.
    Skips base and root if the first element in parts is already an absolute path.
    """
    from gway import gw

    # If the first part is an absolute path, construct directly from it
    first = pathlib.Path(parts[0])
    if first.is_absolute():
        path = pathlib.Path(*parts)
    else:
        path = pathlib.Path(gw.base_path, *parts)

    if not touch and check:
        if not path.exists():
            gw.abort(f"Required resource {path} missing")

    path.parent.mkdir(parents=True, exist_ok=True)
    if touch: path.touch()
    return path


def readlines(*parts, unique=False):
    """Fetch a GWAY resource split by lines. If unique=True, returns a set, otherwise a list."""
    resource_file = resource(*parts)
    lines = [] if not unique else set()
    if os.path.exists(resource_file):
        with open(resource_file, "r") as f:
            for line in f:
                line = line.strip()
                if line:
                    if unique:
                        lines.add(line)
                    else:
                        lines.append(line)
    return lines
                    

def test(root: str = 'tests', filter=None):
    """Execute all automatically detected test suites."""
    import unittest
    from gway import gw

    print("Running the test suite...")

    # Define a custom pattern to include files matching the filter
    def is_test_file(file):
        # If no filter, exclude files starting with '_'
        if filter:
            return file.endswith('.py') and filter in file
        return file.endswith('.py') and not file.startswith('_')

    # List all the test files manually and filter
    test_files = [
        os.path.join(root, f) for f in os.listdir(root)
        if is_test_file(f)
    ]

    # Load the test suite manually from the filtered list
    test_loader = unittest.defaultTestLoader
    test_suite = unittest.TestSuite()

    for test_file in test_files:
        test_suite.addTests(test_loader.discover(
            os.path.dirname(test_file), pattern=os.path.basename(test_file)))
    
    # Run the tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    gw.info(f"Test results: {str(result).strip()}")
    return result.wasSuccessful()


def _strip_types(sig: str) -> str:
    try:
        node = ast.parse(f"def _({sig}): pass").body[0]
        args = node.args
        param_names = []
        for arg in args.args:
            param_names.append(arg.arg)
        if args.vararg:
            param_names.append(f"*{args.vararg.arg}")
        if args.kwarg:
            param_names.append(f"**{args.kwarg.arg}")
        return ", ".join(param_names)
    except Exception:
        return sig  # fallback if parsing fails
    

def help(*args, full=False):
    from gway import gw
    import os, textwrap, ast, sqlite3

    gw.info(f"Help on {' '.join(args)} requested")

    def extract_gw_refs(source):
        refs = set()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return refs

        class GwVisitor(ast.NodeVisitor):
            def visit_Attribute(self, node):
                parts = []
                cur = node
                while isinstance(cur, ast.Attribute):
                    parts.append(cur.attr)
                    cur = cur.value
                if isinstance(cur, ast.Name) and cur.id == "gw":
                    parts.append("gw")
                    full = ".".join(reversed(parts))[3:]  # remove "gw."
                    refs.add(full)
                self.generic_visit(node)

        GwVisitor().visit(tree)
        return refs

    db_path = gw.resource("data", "help.sqlite")
    if not os.path.isfile(db_path):
        gw.release.build_help_db()

    joined_args = " ".join(args).strip().replace("-", "_")
    norm_args = [a.replace("-", "_").replace("/", ".") for a in args]

    with gw.sql.connect(db_path, row_factory=True) as cur:
        if not args:
            cur.execute("SELECT DISTINCT project FROM help")
            return {"Available Projects": sorted([row["project"] for row in cur.fetchall()])}

        rows = []

        # Case 1: help("web.site.view_help")
        if len(norm_args) == 1 and "." in norm_args[0]:
            parts = norm_args[0].split(".")
            if len(parts) >= 2:
                project = ".".join(parts[:-1])
                function = parts[-1]
                cur.execute("SELECT * FROM help WHERE project = ? AND function = ?", (project, function))
                rows = cur.fetchall()
                if not rows:
                    try:
                        cur.execute("SELECT * FROM help WHERE help MATCH ?", (f'"{norm_args[0]}"',))
                        rows = cur.fetchall()
                    except sqlite3.OperationalError as e:
                        gw.warning(f"FTS query failed for {norm_args[0]}: {e}")
            else:
                return {"error": f"Could not parse dotted input: {norm_args[0]}"}

        # Case 2: help("web", "view_help") or help("builtin", "hello_world")
        elif len(norm_args) >= 2:
            *proj_parts, maybe_func = norm_args
            project = ".".join(proj_parts)
            function = maybe_func
            cur.execute("SELECT * FROM help WHERE project = ? AND function = ?", (project, function))
            rows = cur.fetchall()
            if not rows:
                fuzzy_query = ".".join(norm_args)
                try:
                    cur.execute("SELECT * FROM help WHERE help MATCH ?", (f'"{fuzzy_query}"',))
                    rows = cur.fetchall()
                except sqlite3.OperationalError as e:
                    gw.warning(f"FTS fallback failed for {fuzzy_query}: {e}")

        # Final fallback: maybe it's a builtin like help("hello_world")
        if not rows and len(norm_args) == 1:
            name = norm_args[0]
            cur.execute("SELECT * FROM help WHERE project = ? AND function = ?", ("builtin", name))
            rows = cur.fetchall()

        if not rows:
            fuzzy_query = ".".join(norm_args)
            try:
                cur.execute("SELECT * FROM help WHERE help MATCH ?", (f'"{fuzzy_query}"',))
                rows = cur.fetchall()
            except sqlite3.OperationalError as e:
                gw.warning(f"FTS final fallback failed for {fuzzy_query}: {e}")
                return {"error": f"No help found and fallback failed for: {joined_args}"}

        results = []
        for row in rows:
            project = row["project"]
            function = row["function"]
            prefix = f"gway {project} {function.replace('_', '-')}" if project != "builtin" else f"gway {function.replace('_', '-')}"
            entry = {
                "Project": project,
                "Function": function,
                "Sample CLI": prefix,
                "References": sorted(extract_gw_refs(row["source"])),
            }
            if full:
                entry["Full Code"] = row["source"]
            else:
                entry["Signature"] = textwrap.fill(row["signature"], 100).strip()
                entry["Docstring"] = row["docstring"].strip() if row["docstring"] else None
                entry["TODOs"] = row["todos"].strip() if row["todos"] else None
            results.append({k: v for k, v in entry.items() if v})

        return results[0] if len(results) == 1 else {"Matches": results}


def sample_cli_args(func):
    """Generate a sample CLI string for a function."""
    from gway import gw
    if not callable(func):
        func = gw[str(func).replace("-", "_")]
    sig = inspect.signature(func)
    parts = []
    seen_kw_only = False

    for name, param in sig.parameters.items():
        kind = param.kind

        if kind == inspect.Parameter.VAR_POSITIONAL:
            parts.append(f"[{name}1 {name}2 ...]")
        elif kind == inspect.Parameter.VAR_KEYWORD:
            parts.append(f"[--{name}1 val1 --{name}2 val2 ...]")
        elif kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD):
            if not seen_kw_only:
                parts.append(f"<{name}>")
            else:
                parts.append(f"--{name.replace('_', '-')} <val>")
        elif kind == inspect.Parameter.KEYWORD_ONLY:
            seen_kw_only = True
            cli_name = f"--{name.replace('_', '-')}"
            if param.annotation is bool or isinstance(param.default, bool):
                parts.append(f"[{cli_name} | --no-{name.replace('_', '-')}]")
            else:
                parts.append(f"{cli_name} <val>")

    return " ".join(parts)


def sigils(*args: str):
    """List the valid sigils found in any of the given args."""
    from .sigils import Sigil
    text = "\n".join(args)
    return Sigil(text).list_sigils()


def run_recipe(*script: str, **context):
    """
    Run commands parsed from a .gwr file, falling back to the 'recipes/' resource bundle.
    Recipes are gway scripts composed of one command per line with optional comments.
    """
    from .console import load_recipe, process_commands
    from gway import gw

    gw.debug(f"run_recipe called with script tuple: {script!r}")

    # Ensure the last element ends with '.gwr'
    if not script[-1].endswith(".gwr"):
        script = script[:-1] + (script[-1] + ".gwr",)
        gw.debug(f"Appended .gwr extension, new script tuple: {script!r}")

    # Try to resolve the script as given
    try:
        script_path = gw.resource(*script, check=True)
        gw.debug(f"Found script at: {script_path}")
    except (FileNotFoundError, KeyError) as first_exc:
        # Fallback: look in the 'recipes' directory of the package
        gw.debug(f"Script not found at {script!r}: {first_exc!r}")
        try:
            script_path = gw.resource("recipes", *script)
            gw.debug(f"Found script in 'recipes/': {script_path}")
        except Exception as second_exc:
            # If still not found, re-raise with a clear message
            msg = (
                f"Could not locate script {script!r} "
                f"(tried direct lookup and under 'recipes/')."
            )
            gw.debug(f"{msg} Last error: {second_exc!r}")
            raise FileNotFoundError(msg) from second_exc

    # Load and run the recipe
    command_sources, comments = load_recipe(script_path)
    if comments:
        gw.debug("Recipe comments:\n" + "\n".join(comments))
    return process_commands(command_sources, **context)


def run(*script: str, **context):
    from gway import gw
    # TODO: If args provided for script don't seem to be recipe file 
    # (we could catch the exception), see if we can write them joined by line breaks into 
    # file at path gw.resource('work', 'run', gw.uuid, 'script.cdv')
    return gw.run_recipe(*script, **context)


def unwrap(obj: Any, expected: Optional[Type] = None) -> Any:
    """
    Function unwrapper that digs through __wrapped__, iterables, and closures.
    """
    def unwrap_closure(fn: FunctionType, expected: Type) -> Optional[Any]:
        if fn.__closure__:
            for cell in fn.__closure__:
                val = cell.cell_contents
                result = unwrap(val, expected)
                if result is not None:
                    return result
        return None

    if expected is not None:
        if isinstance(obj, expected):
            return obj

        if callable(obj):
            # First try inspect.unwrap
            try:
                unwrapped = inspect.unwrap(obj)
            except Exception:
                unwrapped = obj

            if isinstance(unwrapped, expected):
                return unwrapped

            # Then search closure variables
            found = unwrap_closure(unwrapped, expected)
            if found is not None:
                return found

        # If obj is a container, scan recursively
        if isinstance(obj, Iterable) and not isinstance(obj, (str, bytes, bytearray)):
            for item in obj:
                found = unwrap(item, expected)
                if found is not None:
                    return found

        return None

    # expected not provided → default unwrap
    if callable(obj):
        try:
            return inspect.unwrap(obj)
        except Exception:
            return obj

    return obj

