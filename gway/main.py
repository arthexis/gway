import os
import sys
import time
import inspect
import logging
import importlib.util
import argparse

from .logging import setup_logging

VERBOSE = False
_print = print  # Store original print

logger = logging.getLogger(__name__)


def print(*args, **kwargs):
    """Custom print function to handle verbose output."""
    logger.info(*args, **kwargs)
    if VERBOSE or ("verbose" in kwargs and kwargs["verbose"]):
        _print(*args, **kwargs)


def abort(message: str, exit_code: int = 1):
    """Abort with error message."""
    logger.error(message)
    print(f"Error: {message}")
    sys.exit(exit_code)


def load_project(project_name: str, project_root: str = None) -> tuple:
    """Load a project module dynamically."""
    if project_root is None:
        project_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "projects")

    if not os.path.isdir(project_root):
        abort(f"Invalid project root: {project_root}")

    project_parts = project_name.split(".")
    project_file = os.path.join(project_root, *project_parts) + ".py"

    if not os.path.isfile(project_file):
        abort(f"Project file '{project_file}' does not exist.")

    module_name = project_name.replace(".", "_")
    spec = importlib.util.spec_from_file_location(module_name, project_file)
    project_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(project_module)

    project_functions = {
        name: obj for name, obj in inspect.getmembers(project_module)
        if inspect.isfunction(obj) and not name.startswith("_")
    }
    return project_module, project_functions


def load_builtins() -> dict:
    """Load built-in functions from the builtins module.
    """
    import builtins
    builtins_functions = {
        name: obj for name, obj in inspect.getmembers(builtins)
        if inspect.isfunction(obj) and not name.startswith("_")
    }
    return builtins_functions


def show_functions(project_functions: dict):
    """Display available functions in project."""
    print("Available functions:")
    for name, func in project_functions.items():
        doc = func.__doc__.splitlines()[0] if func.__doc__ else "No docstring"
        print(f"  - {name}: {doc}")


def add_function_args(subparser, func_obj):
    for arg_name, param in inspect.signature(func_obj).parameters.items():
        arg_opts = {}
        if param.annotation == bool:
            arg_opts["action"] = "store_true"
        else:
            arg_opts["type"] = param.annotation if param.annotation != param.empty else str
        if param.default != param.empty:
            arg_opts["default"] = param.default
        else:
            arg_opts["required"] = True
        subparser.add_argument(f"--{arg_name}", **arg_opts)


def cli_main():
    """Main CLI entry point."""
    global VERBOSE

    parser = argparse.ArgumentParser(description="Dynamic Project CLI")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("-p", "--project-root", type=str, help="Specify project directory")
    parser.add_argument("-t", "--timed", action="store_true", help="Enable timing")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("project_name", type=str, nargs="?", help="Project to load")

    args, unknown = parser.parse_known_args()

    if args.verbose:
        VERBOSE = True

    loglevel = "DEBUG" if args.debug else "INFO"
    setup_logging(logfile="gway.log", loglevel=loglevel, app_name="gway")

    START_TIME = time.time() if args.timed else None

    if not args.project_name:
        parser.print_help()
        sys.exit(1)

    # Load project
    project_module, project_functions = load_project(args.project_name, args.project_root)

    # Now create a SECOND parser for function and its options
    func_parser = argparse.ArgumentParser(description=f"Functions for project {args.project_name}")
    func_subparsers = func_parser.add_subparsers(dest="function_name", required=True)

    for func_name, func_obj in project_functions.items():
        sp = func_subparsers.add_parser(func_name, help=(func_obj.__doc__ or "No docstring").splitlines()[0])
        add_function_args(sp, func_obj)

    func_args = func_parser.parse_args(unknown)

    if not func_args.function_name:
        show_functions(project_functions)
        sys.exit(1)

    func_obj = project_functions.get(func_args.function_name)
    if not func_obj:
        abort(f"Function '{func_args.function_name}' not found.")

    try:
        func_kwargs = {
            k: v for k, v in vars(func_args).items()
            if k in inspect.signature(func_obj).parameters
        }
        result = func_obj(**func_kwargs)
        print(f"Function '{func_args.function_name}' executed successfully with result: {result}")
    except Exception as e:
        abort(f"Error executing function '{func_args.function_name}': {e}")

    if START_TIME:
        elapsed_time = time.time() - START_TIME
        print(f"Elapsed time: {elapsed_time:.2f} seconds")
