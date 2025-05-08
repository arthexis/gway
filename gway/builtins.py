import os
import inspect
import pathlib
import textwrap

from colorama import init as colorama_init, Fore, Style


# Avoid importing Gateway at the top level in this file specifically (circular import)
    

def hello_world(name: str = "World", greeting: str = "Hello"):
    """Smoke test function."""
    from gway import gw

    message = f"{greeting.title()}, {name.title()}!"
    if hasattr(gw, "hello_world"): print(message)
    else: print("Greetings not found.")
    return locals()


def abort(message: str, exit_code: int = 1) -> int:
    """Abort with error message."""
    from gway import gw

    gw.error(message)
    print(f"Halting: {message}")
    raise SystemExit(exit_code)


def envs(filter: str = None) -> dict:
    """Return all environment variables in a dictionary."""
    if filter:
        filter = filter.upper()
        return {k: v for k, v in os.environ.items() if filter in k}
    else: 
        return os.environ.copy()


def version() -> str:
    """Return the version of the package."""
    from gway import gw

    # Get the version in the VERSION file
    version_path = gw.resource("VERSION")
    if os.path.exists(version_path):
        with open(version_path, "r") as version_file:
            version = version_file.read().strip()
            return version
    else:
        print("VERSION file not found.")
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


def readlines(*parts, base=None, unique=False):
    """Fetch a GWAY resource split by lines. If unique=True, returns a set, otherwise a list."""
    resource_file = resource(*parts, base=None)
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
            cur.execute("SELECT * FROM help WHERE help MATCH ?", (query,))
        elif len(args) == 2:
            project = args[0].replace("-", "_")
            func = args[1].replace("-", "_")
            cur.execute("SELECT * FROM help WHERE project = ? AND function = ?", (project, func))
        else:
            print("Too many arguments.")
            return

        rows = cur.fetchall()
        if not rows:
            print(f"No help found for: {' '.join(args)}")
            return

        # TODO: Example code generation is not as expected. Currently it just mangles the signature a little
        # However that doesn't work because of type annotations. Instead just make it look like a regular function call

        results = []
        for row in rows:
            results.append({k:v for k,v in {
                "Project": row["project"],
                "Function": row["function"],
                "Signature": textwrap.fill(row["signature"], 100).strip(),
                "Docstring": row["docstring"].strip() if row["docstring"] else None,  # <--- trim leading/trailing blank lines
                "TODOs": row["todos"].strip() if row["todos"] else None,          # <--- same here
                "Example CLI": f"gway {row['project']} {row['function']}",
                "Example Code": textwrap.fill(
                    f"gw.{row['project']}.{row['function']}({row['signature']})", 100
                ).strip(),  # <--- remove any trailing blank lines
                **({"Full Code": row["source"]} if full_code else {})
            }.items() if v})

        return results[0] if len(results) == 1 else {"Matches": results}


def sigils(*args: str):
    from .sigils import Sigil
    text = "\n".join(args)
    return Sigil(text).list_sigils()
