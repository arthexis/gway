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
    

def enum(*args):
    for i, arg in enumerate(args):
        print(f"{i} - {arg}")


_print = print
_INSERT_NL = False

def print(text, *, max_depth=10, _current_depth=0):
    """Recursively prints an object with colorized output without extra spacing."""
    global _INSERT_NL
    if _INSERT_NL:
        _print()
    # Show which function called print
    try:
        print_frame = inspect.stack()[2]
    except IndexError:
        print_frame = inspect.stack()[1]
    print_origin = f"{print_frame.function}() in {print_frame.filename}:{print_frame.lineno}"
    logger.debug(f"From {print_origin}:\n {text}")

    colorama_init(strip=False)

    if _current_depth > max_depth:
        _print(f"{Fore.YELLOW}...{Style.RESET_ALL}", end="")
        return

    if isinstance(text, dict):
        for k, v in text.items():
            if k.startswith("_"):
                continue
            key_str = f"{Fore.BLUE}{Style.BRIGHT}{k}{Style.RESET_ALL}"
            colon = f"{Style.DIM}: {Style.RESET_ALL}"
            _print(f"{key_str}{colon} {v}")
    elif isinstance(text, list):
        for i, item in enumerate(text):
            if i > 0:
                _print(end="")  # No comma separator for items
            print(item, max_depth=max_depth, _current_depth=_current_depth + 1)
    elif isinstance(text, str):
        _print(f"{Fore.GREEN}{text}{Style.RESET_ALL}", end="")  # No extra newline after string
    elif callable(text):
        try:
            func_name = text.__name__.replace("__", " ").replace("_", "-")
            sig = inspect.signature(text)
            args = []
            for param in sig.parameters.values():
                name = param.name.replace("__", " ").replace("_", "-")
                if param.default is param.empty:
                    args.append(name)
                else:
                    args.append(f"--{name} {param.default}")
            formatted = " ".join([func_name] + args)
            _print(f"{Fore.MAGENTA}{formatted}{Style.RESET_ALL}", end="")
        except Exception:
            _print(f"{Fore.RED}<function>{Style.RESET_ALL}", end="")
    else:
        _print(f"{Fore.GREEN}{str(text)}{Style.RESET_ALL}", end="")  # No extra newline
    _INSERT_NL = True


def version() -> str:
    """Return the version of the package."""
    from gway import Gateway

    # Get the version in the VERSION file
    version_path = Gateway().resource("VERSION")
    if os.path.exists(version_path):
        with open(version_path, "r") as version_file:
            version = version_file.read().strip()
            logger.info(f"Current version: {version}")
            return version
    else:
        logger.error("VERSION file not found.")
        return "unknown"


def resource(*parts, base=None, touch=False):
    """
    Construct a path relative to the base, or the Gateway root if not specified.
    Assumes last part is a file and creates parent directories along the way.
    """
    from gway import Gateway

    path = pathlib.Path(base or Gateway().root, *parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    if touch:
        path.touch()

    return path


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
    return result.wasSuccessful()


def help(*args, full_code=False):
    """
    Display help information for a gway function.

    Usage:
        help("builtin_function")
        help("project", "function_name")
        help("project")  # NEW: Show help for all functions in a project
    """
    from gway import Gateway
    gway = Gateway()

    # Determine the function and context
    if len(args) == 1:
        name = args[0].replace("-", "_")
        func_obj = getattr(gway, name, None)

        if func_obj and callable(func_obj):
            # It's a direct function (builtin)
            location = "builtin"
            func_name = name
        elif hasattr(gway, name):
            # It's a project/module: show help on all functions inside
            module = getattr(gway, name)
            output = {
                "Project": name,
                "Module": str(module),
                "Available Functions": sorted(
                    attr for attr in dir(module)
                    if not attr.startswith("_") and callable(getattr(module, attr))
                )
            }
            return output
        else:
            gway.print(f"Function or project not found: {args[0]}")
            return
    elif len(args) == 2:
        location = args[0].replace("-", "_")
        func_name = args[1].replace("-", "_")
        module = getattr(gway, location, None)
        func_obj = getattr(module, func_name, None) if module else None
    else:
        gway.print("Usage: help('builtin') or help('project', 'function')")
        return

    if not func_obj or not callable(func_obj):
        gway.print(f"Function not found: {' '.join(args)}")
        return

    doc = inspect.getdoc(func_obj) or "(No docstring available)"
    sig = inspect.signature(func_obj)

    cli_parts = []
    code_parts = []
    for name, param in sig.parameters.items():
        cli_flag = f"--{name.replace('_', '-')}"
        is_required = param.default == inspect.Parameter.empty
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            cli_parts.append("[<args>...]")
            code_parts.append("*args")
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            cli_parts.append("[--kwargs key=value ...]")
            code_parts.append("**kwargs")
        elif param.annotation == bool or isinstance(param.default, bool):
            cli_parts.append(f"[--{name.replace('_', '-')}/--no-{name.replace('_', '-')}]")
            code_parts.append(f"{name}={param.default}")
        elif is_required:
            cli_parts.append(f"<{name}>")
            code_parts.append(name)
        else:
            cli_parts.append(f"{cli_flag} {param.default}")
            code_parts.append(f"{name}={repr(param.default)}")

    cli_call = f"gway {args[0]}" if len(args) == 1 else f"gway {args[0]} {args[1]}"
    if cli_parts:
        cli_call += " " + " ".join(cli_parts)

    code_call = f"gway.{func_name}" if len(args) == 1 else f"gway.{args[0]}.{func_name}"
    code_call += f"({', '.join(code_parts)})"

    todos = []
    try:
        source_lines = inspect.getsourcelines(func_obj)[0]
        todo_block = None

        for line in source_lines:
            stripped = line.strip()
            if "# TODO" in stripped:
                todo_text = stripped.split("# TODO", 1)[-1].strip()
                if todo_block:
                    todos.append("\n".join(todo_block))
                todo_block = [f"TODO: {todo_text}"]
            elif todo_block and (stripped.startswith("#") or not stripped):
                comment = stripped.lstrip("#").strip()
                if comment:
                    todo_block.append(comment)
            elif todo_block:
                todos.append("\n".join(todo_block))
                todo_block = None

        if todo_block:
            todos.append("\n".join(todo_block))
    except Exception as e:
        todos = [f"Error extracting TODOs: {e}"]

    result = {
        "Signature": f"{func_name}{sig}",
        "Docstring": f"{textwrap.fill(doc, width=80)}",
        "Example CLI": cli_call, 
        "Example Code": code_call,
        "TODOs": todos or None
    }

    if full_code:
        try:
            result["Full Code"] = "".join(inspect.getsourcelines(func_obj)[0])
        except Exception as e:
            result["Full Code"] = f"(Could not retrieve code: {e})"

    return result


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


def scratch():
    from gway import Gateway
    gway = Gateway()
    # TODO: Use this function for quick tests

