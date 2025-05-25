import os
import ast
import pathlib
import textwrap
import datetime
import time as _time


# Avoid importing Gateway at the top level in this file specifically (circular import)
# Instead, use "from gway import gw" inside the function definitions themselves
# Trust me, bro. It works.
    

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


def resource(*parts, touch=False, check=False, temp=False):
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
    elif temp:
        path = pathlib.Path("temp", *parts)
    else:
        path = pathlib.Path(gw.base_path, *parts)

    if not touch and check:
        assert path.exists(), f"Resource {path} missing"

    path.parent.mkdir(parents=True, exist_ok=True)
    if touch:
        path.touch()

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

    with gw.database.connect(db_path, row_factory=True) as cur:

        if len(args) == 0:
            cur.execute("SELECT DISTINCT project FROM help")
            return {"Available Projects": sorted([row["project"] for row in cur.fetchall()])}

        elif len(args) == 1:
            query = args[0].replace("-", "_")
            parts = query.split(".")
            exact_rows = []

            if len(parts) == 2:
                project, function = parts
                cur.execute("SELECT * FROM help WHERE project = ? AND function = ?", (project, function))
                exact_rows = cur.fetchall()

            cur.execute("SELECT * FROM help WHERE help MATCH ?", (query,))
            fuzzy_rows = [row for row in cur.fetchall() if row not in exact_rows]
            rows = exact_rows + fuzzy_rows

        elif len(args) == 2:
            project = args[0].replace("-", "_")
            func = args[1].replace("-", "_")
            cur.execute("SELECT * FROM help WHERE project = ? AND function = ?", (project, func))
            rows = cur.fetchall()
        else:
            print("Too many arguments.")
            return

        if not rows:
            print(f"No help found for: {' '.join(args)}")
            return

        results = []
        for row in rows:
            example_code = f"gw.{row['project']}.{row['function']}({_strip_types(row['signature'])})"
            results.append({k: v for k, v in {
                "Project": row["project"],
                "Function": row["function"],
                "Signature": textwrap.fill(row["signature"], 100).strip(),
                "Docstring": row["docstring"].strip() if row["docstring"] else None,
                "TODOs": row["todos"].strip() if row["todos"] else None,
                "Example CLI": f"gway {row['project']} {row['function']}",
                "Example Code": textwrap.fill(example_code, 100).strip(),
                **({"Full Code": row["source"]} if full_code else {})
            }.items() if v})

        return results[0] if len(results) == 1 else {"Matches": results}


def now(*, utc=False) -> "datetime":
    """Return the current datetime object."""
    return datetime.datetime.now(datetime.timezone.utc) if utc else datetime.datetime.now()


def time(*, utc=False) -> str:
    """Return the current time of day as HH:MM:SS."""
    struct_time = _time.gmtime() if utc else _time.localtime()
    return _time.strftime('%H:%M:%S', struct_time)


def timestamp(*, utc=False) -> str:
    """Return the current timestamp in ISO-8601 format."""
    return now(utc=utc).isoformat().replace("+00:00", "Z" if utc else "")


def sigils(*args: str):
    from .sigils import Sigil
    text = "\n".join(args)
    return Sigil(text).list_sigils()


def run_batch(*script: str, **context):
    """Run commands parsed from a .gws file."""
    from .command import load_batch, process_commands
    from gway import gw

    gw.debug(f"{script=}")
    if not script[-1].endswith(".gws"):
        script = script[0:-1] + ((script[-1] + ".gws"), )
    script_path = gw.resource(*script)
    gw.debug(f"{script_path}")

    command_sources, comments = load_batch(script_path)
    gw.debug(f"{chr(10).join(comments)}")  # Optional: log batch comments

    return process_commands(command_sources, **context)


def skip_all(chunk):
    from gway import gw
    gw.info(f"Skiping chunk: {chunk}")
    return False


def log_all(chunk):
    from gway import gw
    gw.info(f"Logging chunk: {chunk}")
    return True
