import os
import ast
import pathlib
import textwrap
from collections.abc import Iterable
from typing import Any, Callable, List, Optional


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


def help(*args, full_code=False):
    from gway import gw

    db_path = gw.resource("data", "help.sqlite")
    if not os.path.isfile(db_path):
        gw.release.build_help_db()

    # 1) Combine all args into a single string, for easy “wiki” detection:
    joined_args = " ".join(args).strip()
    lowercase_args = joined_args.lower().split()

    # 2) If the user explicitly included the token "wiki" anywhere, strip it out
    #    and immediately call gw.wiki.query(...) on what remains.
    if "wiki" in lowercase_args:
        # Build a new query string that omits every “wiki” token
        filtered_words = [w for w in joined_args.split() if w.lower() != "wiki"]
        wiki_query = " ".join(filtered_words).strip()

        if not wiki_query:
            # If they only typed “help wiki” or “wiki”, return a usage hint:
            return {"error": "Please provide a term after 'wiki'. Example: help('wiki', 'python')"}
        else:
            gw.info(f"Help: Detected 'wiki' token. Falling back to gw.wiki.query('{wiki_query}')")
            return gw.wiki.query(wiki_query)

    # 3) Otherwise—proceed with the normal SQLite‐backed help lookup.
    with gw.sql.connect(db_path, row_factory=True) as cur:

        # Case: no arguments → list all available projects
        if len(args) == 0:
            cur.execute("SELECT DISTINCT project FROM help")
            return {"Available Projects": sorted([row["project"] for row in cur.fetchall()])}

        # Case: exactly one argument → try exact match first, then fuzzy MATCH
        elif len(args) == 1:
            query = args[0].replace("-", "_")
            parts = query.split(".")
            exact_rows = []

            if len(parts) == 2:
                project, function = parts
                cur.execute(
                    "SELECT * FROM help WHERE project = ? AND function = ?",
                    (project, function),
                )
                exact_rows = cur.fetchall()

            # Perform a full‐text search on the “help” column
            cur.execute("SELECT * FROM help WHERE help MATCH ?", (query,))
            fuzzy_rows = [row for row in cur.fetchall() if row not in exact_rows]
            rows = exact_rows + fuzzy_rows

        # Case: two arguments → interpret as project + function
        elif len(args) == 2:
            project = args[0].replace("-", "_")
            func = args[1].replace("-", "_")
            cur.execute(
                "SELECT * FROM help WHERE project = ? AND function = ?",
                (project, func),
            )
            rows = cur.fetchall()

        else:
            print("Too many arguments.")
            return

        # 4) If no rows matched, **fall back** to gw.wiki.query on the entire original query
        if not rows:
            gw.info(f"Help: No help found for '{joined_args}'. Falling back to gw.wiki.query.")
            return gw.wiki.query(joined_args)

        # 5) Otherwise, format and return the matching help entries
        results = []
        for row in rows:
            example_code = f"gw.{row['project']}.{row['function']}({_strip_types(row['signature'])})"
            entry = {
                "Project": row["project"],
                "Function": row["function"],
                "Signature": textwrap.fill(row["signature"], 100).strip(),
                "Docstring": row["docstring"].strip() if row["docstring"] else None,
                "TODOs": row["todos"].strip() if row["todos"] else None,
                "Example CLI": f"gway {row['project']} {row['function']}",
                "Example Code": textwrap.fill(example_code, 100).strip(),
            }
            if full_code:
                entry["Full Code"] = row["source"]
            # Filter out any None values
            results.append({k: v for k, v in entry.items() if v})

        return results[0] if len(results) == 1 else {"Matches": results}


h = help


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

r = run

def filter_apps(
    *apps: Any,
    kwarg: Optional[Any] = None,
    selector: Callable[[Any], bool]
) -> List[Any]:
    """
    Collects positional *apps and the single `kwarg` value, flattens any
    iterables (that don’t themselves match selector), and returns only
    those items for which selector(item) is True.
    """
    candidates: List[Any] = []

    # helper to append one candidate or a sequence of them
    def _collect(x: Any):
        if x is None:
            return
        # if x itself matches, take it as a single app
        if selector(x):
            candidates.append(x)
        # else if it’s iterable, drill in
        elif isinstance(x, Iterable):
            for sub in x:
                _collect(sub)
        # otherwise discard it
        else:
            return

    # collect from kwarg first (so kwarg= overrides positional if desired)
    if kwarg is not None:
        _collect(kwarg)

    # then collect from all the rest
    for a in apps:
        _collect(a)

    return candidates

