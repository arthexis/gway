import os
import time
import inspect
import logging
import pathlib
import textwrap

from colorama import init as colorama_init, Fore, Style


# Avoid importing Gateway at the top level in this file specifically (circular import)

logger = logging.getLogger(__name__)


def abort(message: str, exit_code: int = 1) -> int:
    """Abort with error message."""
    logger.error(message)
    print(f"Halting: {message}")
    raise SystemExit(exit_code)
    

def hello_world(name: str = "World", greeting: str = "Hello"):
    """Smoke test function."""
    from gway import Gateway
    gway = Gateway()

    message = f"{greeting.title()}, {name.title()}!"
    if hasattr(gway, "hello_world"): gway.print(message)
    return locals()


def envs(filter: str = None) -> dict:
    """Return all environment variables in a dictionary."""
    if filter:
        filter = filter.upper()
        return {k: v for k, v in os.environ.items() if filter in k}
    else: 
        return os.environ.copy()


_print = print
_INSERT_NL = False

def print(obj, *, max_depth=10, _current_depth=0, _indent=0):
    """YAML-like compact printer with color and proper key-value formatting."""
    global _INSERT_NL
    if _INSERT_NL:
        _print()
    if _current_depth == 0:
        try:
            frame = inspect.stack()[2]
        except IndexError:
            frame = inspect.stack()[1]
        origin = f"{frame.function}() in {frame.filename}:{frame.lineno}"
        import logging
        logging.getLogger("gway").debug(f"From {origin}:\n{obj}")

    colorama_init(strip=False)
    indent = "  " * _indent
    if _current_depth > max_depth:
        _print(f"{indent}{Fore.YELLOW}...{Style.RESET_ALL}")
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).startswith("_"):
                continue
            key_str = f"{Fore.BLUE}{Style.BRIGHT}{k}{Style.RESET_ALL}"
            if isinstance(v, str) and "\n" not in v:
                # Compact single-line value
                _print(f"{indent}{key_str}: {Fore.GREEN}{v.strip()}{Style.RESET_ALL}")
            elif isinstance(v, str) and v.strip() == "":
                continue  # Skip empty strings
            else:
                _print(f"{indent}{key_str}:{Style.RESET_ALL}")
                print(v, max_depth=max_depth, _current_depth=_current_depth + 1, _indent=_indent + 1)
    elif isinstance(obj, list):
        for item in obj:
            print(item, max_depth=max_depth, _current_depth=_current_depth + 1, _indent=_indent)
    elif isinstance(obj, str):
        lines = obj.splitlines()
        for line in lines:
            if line.strip():
                _print(f"{indent}{Fore.GREEN}{line.rstrip()}{Style.RESET_ALL}")
    elif callable(obj):
        try:
            func_name = obj.__name__.replace("__", " ").replace("_", "-")
            sig = inspect.signature(obj)
            args = []
            for param in sig.parameters.values():
                name = param.name.replace("__", " ").replace("_", "-")
                if param.default is param.empty:
                    args.append(name)
                else:
                    args.append(f"--{name}={param.default}")
            formatted = " ".join([func_name] + args)
            _print(f"{indent}{Fore.MAGENTA}{formatted}{Style.RESET_ALL}")
        except Exception:
            _print(f"{indent}{Fore.RED}<function>{Style.RESET_ALL}")
    else:
        _print(f"{indent}{Fore.CYAN}{str(obj)}{Style.RESET_ALL}")

    _INSERT_NL = True


def version() -> str:
    """Return the version of the package."""
    from gway import Gateway

    # Get the version in the VERSION file
    version_path = Gateway().resource("VERSION")
    if os.path.exists(version_path):
        with open(version_path, "r") as version_file:
            version = version_file.read().strip()
            logger.debug(f"Current version: {version}")
            return version
    else:
        logger.error("VERSION file not found.")
        return "unknown"


def resource(*parts, base=None, touch=False, check=False, temp=False):
    """
    Construct a path relative to the base, or the Gateway root if not specified.
    Assumes last part is a file and creates parent directories along the way.
    Skips base and root if the first element in parts is already an absolute path.
    """
    from gway import Gateway

    # If the first part is an absolute path, construct directly from it
    first = pathlib.Path(parts[0])
    if first.is_absolute():
        path = pathlib.Path(*parts)
    elif temp:
        path = pathlib.Path("temp", *parts)
    else:
        path = pathlib.Path(base or Gateway().root, *parts)

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
                    

def run_tests(root: str = 'tests', filter=None):
    """Execute all automatically detected test suites."""
    import unittest
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
    logger.info(f"Test results: {str(result).strip()}")
    return result.wasSuccessful()


def help(*args, full_code=False):
    from gway import Gateway
    gway = Gateway()

    db_path = gway.resource("data", "help.sqlite")
    if not os.path.isfile(db_path):
        gway.print("Help database not found. Run build() first.")
        return

    with gway.database.connect(db_path, row_factory=True) as cur:

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
            gway.print("Too many arguments.")
            return

        rows = cur.fetchall()
        if not rows:
            gway.print(f"No help found for: {' '.join(args)}")
            return

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
                    f"gway.{row['project']}.{row['function']}({row['signature']})", 100
                ).strip(),  # <--- remove any trailing blank lines
                **({"Full Code": row["source"]} if full_code else {})
            }.items() if v})

        return results[0] if len(results) == 1 else {"Matches": results}


def sigils(*args: str):
    from .sigils import Sigil
    text = "\n".join(args)
    return Sigil(text).list_sigils()


def get_tag(func, key, default=None):
    # Unwrap to the original function
    while hasattr(func, '__wrapped__'):
        func = func.__wrapped__
    return getattr(func, 'tags', {}).get(key, default)


def watch_file(filepath, on_change, poll_interval=5.0, logger=None):
    import threading
    stop_event = threading.Event()

    def _watch():
        try:
            last_mtime = os.path.getmtime(filepath)
        except FileNotFoundError:
            last_mtime = None

        while not stop_event.is_set():
            try:
                current_mtime = os.path.getmtime(filepath)
                if last_mtime is not None and current_mtime != last_mtime:
                    if logger:
                        logger.warning(f"File changed: {filepath}")
                    on_change()
                    os._exit(1)
                last_mtime = current_mtime
            except FileNotFoundError:
                pass
            time.sleep(poll_interval)

    thread = threading.Thread(target=_watch, daemon=True)
    thread.start()
    return stop_event

