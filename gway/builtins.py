import os
import sys
import inspect
import logging
import pathlib

# Avoid importing Gateway at the top level in this file specifically (circular import)


logger = logging.getLogger(__name__)


def abort(message: str, exit_code: int = 1, library_mode: bool = None) -> int:
    """Abort with error message."""
    from .gateway import LIBRARY_MODE
    if library_mode is None:
        library_mode = LIBRARY_MODE
    logger.error(message)
    print(f"Halting: {message}")
    
    # Check if we are running in test mode by checking an environment variable
    if os.getenv('TEST_MODE') != '1':  # Only call sys.exit if TEST_MODE is not set
        if not LIBRARY_MODE:
            sys.exit(exit_code)
        else:
            raise SystemExit(exit_code)
    else:
        # In test mode, just print the error and don't exit
        print(f"Abort in TEST_MODE: {message} (exit code {exit_code})")
        return exit_code


def hello_world(name: str = "World", greeting: str = "Hello"):
    """Smoke test function."""
    from gway import Gateway
    gway = Gateway()

    message = f"{greeting.title()}, {name.title()}!"
    if hasattr(gway, "hello_world"):
        gway.print(message)

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
    logger.info(f"From {print_origin}:\n {text}")

    from colorama import init as colorama_init, Fore, Style
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
        _print("[", end="")
        for i, item in enumerate(text):
            if i > 0:
                _print(end="")  # No comma separator for items
            print(item, max_depth=max_depth, _current_depth=_current_depth + 1)
        _print("]", end="")  # Avoid new line after list
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
    """Construct a path relative to the base. Assumes last part is a file and creates parent directories."""
    from gway import Gateway

    path = pathlib.Path(base or Gateway().root, *parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    if touch:
        path.touch()

    return path


def run_tests(root: str = 'tests'):
    """Execute all automatically detected test suites."""
    import unittest

    print("Running the test suite...")
    os.environ['TEST_MODE'] = '1'
    test_loader = unittest.TestLoader()
    test_suite = test_loader.discover(root)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(test_suite)
    os.environ['TEST_MODE'] = '0'
    return result.wasSuccessful()


def help(*args):
    """
    Display help information for a gway function.

    Usage:
        help("builtin_function")
        help("project", "function_name")
    """
    import textwrap
    from gway import Gateway

    gway = Gateway()

    # Determine the function and context
    if len(args) == 1:
        location = "builtin"
        func_name = args[0].replace("-", "_")
        func_obj = getattr(gway, func_name, None)
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

    gway.print(f"Help for `{func_name}` in `{location}`:")
    gway.print(f"Signature: {func_name}{sig}")
    gway.print(f"Docstring: {textwrap.fill(doc, width=80)}")
    gway.print(f"Example CLI: {cli_call}")
    gway.print(f"Example Code: {code_call}")


def sigils(*args: str):
    from .sigils import Sigil
    text = "\n".join(args)
    return Sigil(text).list_sigils()
