import os
import sys
import inspect
import logging
import pathlib


logger = logging.getLogger(__name__)


def abort(message: str, exit_code: int = 1, library_mode: bool = None) -> int:
    """Abort with error message."""
    from .gateway import LIBRARY_MODE
    if library_mode is None:
        library_mode = LIBRARY_MODE
    logger.error(message)
    print(f"Error: {message}")
    
    # Check if we are running in test mode by checking an environment variable
    if os.getenv('TEST_MODE') != '1':  # Only call sys.exit if TEST_MODE is not set
        if not LIBRARY_MODE:
            sys.exit(exit_code)
        else:
            raise SystemExit(exit_code)
    else:
        # In test mode, just print the error and don't exit
        print(f"Test mode: {message} (exit code {exit_code})")
        return exit_code


def hello_world(name: str = "World", greeting: str = "Hello"):
    """Smoke test function."""
    from gway import Gateway
    gway = Gateway()

    message = f"{greeting.title()}, {name.title()}!"
    if hasattr(gway, "hello_world"):
        gway.print(message)


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

def print(obj, *, max_depth=10, _current_depth=0):
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
    logger.info(f"From {print_origin}:\n {obj}")

    from colorama import init as colorama_init, Fore, Style
    colorama_init(strip=False)

    if _current_depth > max_depth:
        _print(f"{Fore.YELLOW}...{Style.RESET_ALL}", end="")
        return

    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.startswith("_"):
                continue
            key_str = f"{Fore.BLUE}{Style.BRIGHT}{k}{Style.RESET_ALL}"
            colon = f"{Style.DIM}: {Style.RESET_ALL}"
            _print(f"{key_str}{colon} {v}")
    elif isinstance(obj, list):
        _print("[", end="")
        for i, item in enumerate(obj):
            if i > 0:
                _print(end="")  # No comma separator for items
            print(item, max_depth=max_depth, _current_depth=_current_depth + 1)
        _print("]", end="")  # Avoid new line after list
    elif isinstance(obj, str):
        _print(f"{Fore.GREEN}{obj}{Style.RESET_ALL}", end="")  # No extra newline after string
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
                    args.append(f"--{name} {param.default}")
            formatted = " ".join([func_name] + args)
            _print(f"{Fore.MAGENTA}{formatted}{Style.RESET_ALL}", end="")
        except Exception:
            _print(f"{Fore.RED}<function>{Style.RESET_ALL}", end="")
    else:
        _print(f"{Fore.GREEN}{str(obj)}{Style.RESET_ALL}", end="")  # No extra newline
    _INSERT_NL = True


def version() -> str:
    """Return the version of the package."""
    from gway import Gateway
    gway = Gateway()

    # Get the version in the VERSION file
    version_path = gway.resource("VERSION")
    if os.path.exists(version_path):
        with open(version_path, "r") as version_file:
            version = version_file.read().strip()
            logger.info(f"Current version: {version}")
            return version
    else:
        logger.error("VERSION file not found.")
        return "unknown"
    
    