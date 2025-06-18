# gway/builtins.py

import os
import re
import sys
import html
import code
import random
import inspect
import collections.abc
from collections.abc import Iterable, Mapping, Sequence
from types import FunctionType
from typing import Any, Optional, Type, List


# Avoid importing Gateway at the top level in this file specifically (circular import)
# Instead, use "from gway import gw" inside the function definitions themselves
    

def hello_world(name: str = "World", *, greeting: str = "Hello"):
    """Smoke test function."""
    from gway import gw

    message = f"{greeting.title()}, {name.title()}!"
    if hasattr(gw, "hello_world"): 
        if not gw.silent:
            print(message)
        else:
            print(f"{gw.silent=}")
    else: 
        print("Greeting protocol not found ((serious smoke)).")
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


def normalize_ext(e):
    return e if e.startswith('.') else f'.{e}'

...


def resource(*parts, touch=False, check=False, text=False):
    """
    Construct a pathlib.Path relative to the base, or Gateway root if unspecified.
    (Getting a file from your root is called "resourcing it" in GWAY parlance.)

    Assumes the last part is a filename and creates parent directories along the way.
    Skips base and root if the first element in parts is already an absolute path.

    Args:
        *parts: Path components, like ("subdir", "file.txt").
        touch (bool): If True, creates the file if it doesn't exist.
        check (bool): If True, aborts if the file doesn't exist and touch is False.
        text (bool): If True, returns the text contents of the file instead of the path.

    Returns:
        pathlib.Path | str: The constructed path, or file contents if text=True.
    """
    import pathlib
    from gway import gw

    # Build path
    first = pathlib.Path(parts[0])
    if first.is_absolute():
        path = pathlib.Path(*parts)
    else:
        path = pathlib.Path(gw.base_path, *parts)

    # Safety check
    if not touch and check and not path.exists():
        gw.abort(f"Required resource {path} missing")

    # Ensure parent directories exist
    path.parent.mkdir(parents=True, exist_ok=True)

    # Optionally create the file
    if touch:
        path.touch()

    # Return text contents or path
    if text:
        try:
            return path.read_text(encoding="utf-8")
        except Exception as e:
            gw.abort(f"Failed to read {path}: {e}")
    return path


def resource_list(*parts, ext=None, prefix=None, suffix=None):
    """
    List all files in a resourced directory that match optional filters.

    This builds a path just like `resource`, but treats it as a directory,
    then lists all files inside that match the given extension, prefix, and/or suffix.

    Args:
        *parts: Path components like ("subdir",).
        ext (str): Optional file extension to match, e.g., ".txt".
        prefix (str): Optional filename prefix to match.
        suffix (str): Optional filename suffix to match.

    Returns:
        list[pathlib.Path]: Sorted list of matching files by creation time (oldest first).
    """
    from gway import gw

    # Build the base directory path using resource
    base_dir = resource(*parts)
    if not base_dir.exists() or not base_dir.is_dir():
        gw.abort(f"Resource directory {base_dir} does not exist or is not a directory")

    # Gather matching files
    matches = []
    for item in base_dir.iterdir():
        if not item.is_file():
            continue
        name = item.name
        if ext and not name.endswith(ext):
            continue
        if prefix and not name.startswith(prefix):
            continue
        if suffix and not name.endswith(suffix):
            continue
        matches.append(item)

    # Sort by creation time (ascending)
    matches.sort(key=lambda p: p.stat().st_ctime)
    return matches

...


def test(root: str = 'tests', filter=None):
    """Execute all automatically detected test suites, logging to logs/test.log."""
    import unittest
    import os
    from gway import gw
    from gway.logging import use_logging

    with use_logging(logfile="test.log", logdir="logs", prog_name="gway",
                     debug=getattr(gw, "debug", False),
                     loglevel=getattr(gw, "loglevel", "INFO"),
                     verbose=getattr(gw, "verbose", False)):
        print("Running the test suite...")

        def is_test_file(file):
            if filter:
                return file.endswith('.py') and filter in file
            return file.endswith('.py') and not file.startswith('_')

        test_files = [
            os.path.join(root, f) for f in os.listdir(root)
            if is_test_file(f)
        ]

        test_loader = unittest.defaultTestLoader
        test_suite = unittest.TestSuite()

        for test_file in test_files:
            test_suite.addTests(test_loader.discover(
                os.path.dirname(test_file), pattern=os.path.basename(test_file)))

        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(test_suite)
        gw.info(f"Test results: {str(result).strip()}")

    # after the block, logs restore to normal!

    return result.wasSuccessful()

...


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

    with gw.sql.open_connection(db_path, row_factory=True) as cur:
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


def infer_type(value, default=None, **types):
    """
    Try casting `value` to each provided type. If a cast succeeds, 
    returns the corresponding key (name). If none succeed, returns default.
    
    Example:
        gw.infer_type("42", INTEGER=int, REAL=float)  # => "INTEGER"
        gw.infer_type("hello", INTEGER=int, default="TEXT")  # => "TEXT"
    """
    for name, caster in types.items():
        try:
            caster(value)
            return name
        except Exception:
            continue
    return default

...


def run_recipe(*script: str, **context):
    """
    Run commands parsed from a .gwr file, falling back to the 'recipes/' resource bundle.
    Recipes are gway scripts composed of one command per line with optional comments.
    """
    from .console import load_recipe, process
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
    return process(command_sources, **context)


def run(*script: str, **context):
    from gway import gw
    return gw.run_recipe(*script, **context)

...

# Unwrapping is useful for handling one or multiple apps, or other
# objects passed between GWAY functions, using a simplified scheme.

def unwrap_one(obj: Any, expected: Optional[Type] = None) -> Any:
    """
    Returns the first matching unwrapped value from obj.
    """
    return next(_unwrap(obj, expected, first_only=True), None)


def unwrap_all(obj: Any, expected: Optional[Type] = None) -> List[Any]:
    """
    Returns a list of all matching unwrapped values from obj.
    """
    return list(_unwrap(obj, expected, first_only=False))


# Internal recursive helper that yields all matches
def _unwrap(obj: Any, expected: Optional[Type], first_only: bool = True):
    """
    Internal generator that recursively searches through obj.
    If first_only is True, yields the first match and stops.
    """
    def unwrap_closure(fn):
        # Only unwrap closures for *actual* functions with __closure__
        if isinstance(fn, FunctionType) and getattr(fn, "__closure__", None):
            for cell in fn.__closure__:
                try:
                    val = cell.cell_contents
                except Exception:
                    continue
                yield from _unwrap(val, expected, first_only)
                if first_only:
                    return

    if expected is not None:
        if isinstance(obj, expected):
            yield obj
            if first_only:
                return

        if callable(obj):
            try:
                unwrapped = inspect.unwrap(obj)
            except Exception:
                unwrapped = obj

            if isinstance(unwrapped, expected):
                yield unwrapped
                if first_only:
                    return

            yield from unwrap_closure(unwrapped)
            if first_only:
                return

        # Only iterate if it's not a string/bytes/bytearray
        if isinstance(obj, Iterable) and not isinstance(obj, (str, bytes, bytearray)):
            for item in obj:
                yield from _unwrap(item, expected, first_only)
                if first_only:
                    return
    else:
        # No expected type, just unwrap callable if possible
        if callable(obj):
            try:
                yield inspect.unwrap(obj)
            except Exception:
                yield obj
        else:
            yield obj

...

# TODO: Remove these functions from gway/builtins.py and relocate them
# to methods of a new class Apeiron in the structs module.


def to_html(obj, **kwargs):
    """
    Convert an arbitrary Python object to structured HTML.
    
    Args:
        obj: The object to convert.
        **kwargs: Optional keyword arguments for customization:
            - class_prefix: Prefix for HTML class names.
            - max_depth: Maximum recursion depth.
            - skip_none: Skip None values.
            - pretty: Insert newlines/indentation.
    
    Returns:
        A string of HTML representing the object.
    """
    class_prefix = kwargs.get("class_prefix", "obj")
    max_depth = kwargs.get("max_depth", 10)
    skip_none = kwargs.get("skip_none", False)
    pretty = kwargs.get("pretty", False)

    def indent(level):
        return "  " * level if pretty else ""

    def _to_html(o, depth=0):
        if depth > max_depth:
            return f'{indent(depth)}<div class="{class_prefix}-max-depth">…</div>'

        if o is None:
            return "" if skip_none else f'{indent(depth)}<div class="{class_prefix}-none">None</div>'

        elif isinstance(o, bool):
            return f'{indent(depth)}<div class="{class_prefix}-bool">{o}</div>'

        elif isinstance(o, (int, float)):
            return f'{indent(depth)}<div class="{class_prefix}-number">{o}</div>'

        elif isinstance(o, str):
            safe = html.escape(o)
            return f'{indent(depth)}<div class="{class_prefix}-string">"{safe}"</div>'

        elif isinstance(o, Mapping):
            html_parts = [f'{indent(depth)}<table class="{class_prefix}-dict">']
            for k, v in o.items():
                if v is None and skip_none:
                    continue
                key_html = html.escape(str(k))
                value_html = _to_html(v, depth + 1)
                html_parts.append(f'{indent(depth+1)}<tr><th>{key_html}</th><td>{value_html}</td></tr>')
            html_parts.append(f'{indent(depth)}</table>')
            return "\n".join(html_parts)

        elif isinstance(o, Sequence) and not isinstance(o, (str, bytes)):
            html_parts = [f'{indent(depth)}<ul class="{class_prefix}-list">']
            for item in o:
                item_html = _to_html(item, depth + 1)
                html_parts.append(f'{indent(depth+1)}<li>{item_html}</li>')
            html_parts.append(f'{indent(depth)}</ul>')
            return "\n".join(html_parts)

        elif hasattr(o, "__dict__"):
            html_parts = [f'{indent(depth)}<div class="{class_prefix}-object">']
            html_parts.append(f'{indent(depth+1)}<div class="{class_prefix}-class-name">{o.__class__.__name__}</div>')
            for k, v in vars(o).items():
                if v is None and skip_none:
                    continue
                value_html = _to_html(v, depth + 2)
                html_parts.append(f'{indent(depth+1)}<div class="{class_prefix}-field"><strong>{html.escape(k)}:</strong> {value_html}</div>')
            html_parts.append(f'{indent(depth)}</div>')
            return "\n".join(html_parts)

        else:
            safe = html.escape(str(o))
            return f'{indent(depth)}<div class="{class_prefix}-other">{safe}</div>'

    return _to_html(obj)


def to_list(obj, flat=False):
    """
    Convert, and optionally flatten, any object into a list with a set of intuitive rules.
    - If `obj` is a string with spaces, commas, colons, or semicolons, split it.
    - If `obj` is a dict or a view (e.g., bottle view dict), return ["key=value", ...].
    - If `obj` is a list or tuple, return it as a list.
    - If `obj` is an iterable, convert to list.
    - Otherwise, return [obj].
    """
    def _flatten(x):
        for item in x:
            if isinstance(item, str) or isinstance(item, bytes):
                yield item
            elif isinstance(item, collections.abc.Mapping):
                for k, v in item.items():
                    yield f"{k}={v}"
            elif isinstance(item, collections.abc.Iterable):
                yield from _flatten(item)
            else:
                yield item

    # Handle string splitting
    if isinstance(obj, str):
        if re.search(r"[ ,;:]", obj):
            result = re.split(r"[ ,;:]+", obj.strip())
            return list(_flatten(result)) if flat else result
        return [obj]

    # Handle mappings (e.g. dicts, views)
    if isinstance(obj, collections.abc.Mapping):
        items = [f"{k}={v}" for k, v in obj.items()]
        return list(_flatten(items)) if flat else items

    # Handle other iterables
    if isinstance(obj, collections.abc.Iterable):
        result = list(obj)
        return list(_flatten(result)) if flat else result

    # Fallback
    return [obj]


def build_url(*args, **kwargs):
    """Build a fully-qualified context-aware URL given a path sequence and query params."""
    from gway import gw
    domain = os.environ.get('BASE_URL', None)
    if not domain:
        default = gw.resolve('http://[WEBSITE_PORT|0.0.0.0]:[WEBSITE_PORT|8888]')
        domain = os.environ.get('SERVER_URL', default)
    try:
        return domain + gw.web.app.build_url(*args, **kwargs)
    except AttributeError:
        return domain + '/'.join(args) 


# Exclude ambiguous characters: 0, O, 1, I, l
_EZ_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghikmnopqrstuvwxyz23456789"

def random_id(length: int = 8, alphabet: str = _EZ_ALPHABET) -> str:
    """
    Generate a readable random ID, avoiding confusing characters.

    Args:
        length: Length of the ID (default 8)
        alphabet: Characters to choose from (default: unambiguous alphanumerics)

    Returns:
        A visually clear, randomly generated string.
    """
    return ''.join(random.choices(alphabet, k=length))


def shell():
    """Launch an interactive Python shell with 'from gway import gw' preloaded."""
    # Try to import gw
    try:
        from gway import gw
    except ImportError as e:
        print(f"Warning: could not import gw from gway ({e})", file=sys.stderr)
        gw = None

    # Build the locals dict for the shell
    local_vars = {'gw': gw}
    banner = (
        "GWAY interactive shell\n"
        "  Type exit() or Ctrl-D to quit."
    )

    # Start the interactive console
    code.interact(banner=banner, local=local_vars)
