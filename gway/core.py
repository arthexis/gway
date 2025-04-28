import os
import sys
import time
import inspect
import logging
import importlib.util
import argparse

from .logging import setup_logging
from .builtins import abort, print, verbose


logger = logging.getLogger(__name__)


def load_project(project_name: str, project_root: str = None) -> tuple:
    if project_root is None:
        project_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "projects")

    if not os.path.isdir(project_root):
        raise FileNotFoundError(f"Invalid project root: {project_root}")

    project_parts = project_name.split(".")
    project_file = os.path.join(project_root, *project_parts) + ".py"

    if not os.path.isfile(project_file):
        raise FileNotFoundError(f"Project file '{project_file}' does not exist.")

    module_name = project_name.replace(".", "_")
    spec = importlib.util.spec_from_file_location(module_name, project_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {project_name}")

    project_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(project_module)

    project_functions = {
        name: obj for name, obj in inspect.getmembers(project_module)
        if inspect.isfunction(obj) and not name.startswith("_")
    }
    return project_module, project_functions


def load_builtins() -> dict:
    """Load only functions defined inside the local builtins.py file."""

    # Make sure to import your OWN 'builtins.py' inside gway package
    builtins_module = importlib.import_module("gway.builtins")

    builtins_functions = {
        name: obj for name, obj in inspect.getmembers(builtins_module)
        if inspect.isfunction(obj)
        and not name.startswith("_")
        and inspect.getmodule(obj) == builtins_module
    }
    return builtins_functions


class Gateway:
    def __init__(self, project_root=None):
        if project_root is None:
            project_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "projects")

        if not os.path.isdir(project_root):
            abort(f"Invalid project root: {project_root}")

        self.project_root = project_root
        self._cache = {}

        # Load built-ins into a dedicated `builtin` object
        self.builtin = type("builtin", (), {})()
        self._load_builtins()

    def _load_builtins(self):
        builtins_functions = load_builtins()
        for name, func in builtins_functions.items():
            setattr(self.builtin, name, func)
            print(f"Loaded builtin function: {name}")

    def __getattr__(self, project_name):
        if project_name in self._cache:
            return self._cache[project_name]

        try:
            module, functions = load_project(project_name, self.project_root)
            project_obj = type(project_name, (), {})()
            for func_name, func_obj in functions.items():
                setattr(project_obj, func_name, func_obj)
            self._cache[project_name] = project_obj
            return project_obj
        except Exception:
            raise AttributeError(f"Project '{project_name}' not found.")


def show_functions(project_functions: dict):
    """Display available functions in project."""
    print("Available functions:")
    for name, func in project_functions.items():
        # Build argument preview
        args_list = []
        for param in inspect.signature(func).parameters.values():
            if param.default != inspect.Parameter.empty:
                default_val = param.default
                if isinstance(default_val, str):
                    default_val = f"{default_val}"
                args_list.append(f"--{param.name} {default_val}")
            else:
                args_list.append(f"--{param.name} <required>")

        args_preview = " ".join(args_list)

        # Extract first non-empty line from docstring
        doc = ""
        if func.__doc__:
            doc_lines = [line.strip() for line in func.__doc__.splitlines()]
            doc = next((line for line in doc_lines if line), "")

        # Print function with tight spacing
        if args_preview:
            print(f"  > {name} {args_preview}")
        else:
            print(f"  > {name}")
        if doc:
            print(f"      {doc}")


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

    parser = argparse.ArgumentParser(description="Dynamic Project CLI")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("-p", "--project-root", type=str, help="Specify project directory")
    parser.add_argument("-t", "--timed", action="store_true", help="Enable timing")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("project_name", type=str, nargs="?", help="Project to load")

    args, unknown = parser.parse_known_args()

    if args.verbose:
        verbose(True)

    loglevel = "DEBUG" if args.debug else "INFO"
    setup_logging(logfile="gway.log", loglevel=loglevel, app_name="gway")

    START_TIME = time.time() if args.timed else None

    if not args.project_name:
        parser.print_help()
        sys.exit(1)

    # Initialize Gateway
    gway = Gateway(project_root=args.project_root)

    # Try to load from gateway first
    project_obj = None
    try:
        project_obj = getattr(gway, args.project_name)
    except AttributeError:
        pass

    # If not found, try to load from builtins
    if project_obj is None:
        try:
            project_obj = getattr(gway.builtin, args.project_name)
        except AttributeError:
            abort(f"Project or builtin '{args.project_name}' not found.")

    # Now check what we loaded
    if callable(project_obj):
        # It's a builtin function
        func_parser = argparse.ArgumentParser(description=f"Builtin {args.project_name}")
        add_function_args(func_parser, project_obj)

        func_args = func_parser.parse_args(unknown)

        try:
            func_kwargs = {
                k: v for k, v in vars(func_args).items()
                if k in inspect.signature(project_obj).parameters
            }
            result = project_obj(**func_kwargs)
        except Exception as e:
            abort(f"Error executing builtin '{args.project_name}': {e}")

    else:
        # Otherwise it's a normal project
        project_functions = {
            name: func for name, func in vars(project_obj).items()
            if callable(func) and not name.startswith("_")
        }

        if not project_functions:
            abort(f"Project '{args.project_name}' does not contain any callable functions.")

        func_parser = argparse.ArgumentParser(description=f"Functions for project {args.project_name}")
        func_subparsers = func_parser.add_subparsers(dest="function_name", required=True)

        for func_name, func_obj in project_functions.items():
            sp = func_subparsers.add_parser(func_name, help=(func_obj.__doc__ or "No docstring").splitlines()[0])
            add_function_args(sp, func_obj)

        if not unknown:
            show_functions(project_functions)
            sys.exit(0)

        func_args = func_parser.parse_args(unknown)

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
