import os
import sys
import importlib
import importlib.util
import inspect
import logging

logger = logging.getLogger(__name__)


def load_project(project_name: str, root: str) -> tuple:
    if not os.path.isdir(root):
        raise FileNotFoundError(f"Invalid project root: {root}")

    # Replace hyphens with underscores in module names
    project_name = project_name.replace("-", "_")

    project_path = os.path.join(root, "projects", *project_name.split("."))
    logger.debug(f"Loading {project_name=}")
    load_mode = None

    if os.path.isdir(project_path) and os.path.isfile(os.path.join(project_path, "__init__.py")):
        # It's a package
        project_file = os.path.join(project_path, "__init__.py")
        module_name = project_name.replace(".", "_")
        load_mode = "package"
    else:
        # It's a single module
        project_file = project_path + ".py"
        if not os.path.isfile(project_file):
            raise FileNotFoundError(f"Project file or package not found: {project_file}")
        module_name = project_name.replace(".", "_")
        load_mode = "module"

    logger.debug(f"Loading as {load_mode} {module_name}")
    spec = importlib.util.spec_from_file_location(module_name, project_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {project_name}")

    project_module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = project_module  # Important for relative imports
    spec.loader.exec_module(project_module)

    if load_mode == "module":
        project_functions = {
            name: obj for name, obj in inspect.getmembers(project_module, inspect.isfunction)
            if not name.startswith("_") and obj.__module__ == project_module.__name__
        }
    else:
        project_functions = {
            name: obj for name, obj in inspect.getmembers(project_module, inspect.isfunction)
            if not name.startswith("_") 
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


def show_functions(functions: dict):
    """Display available functions in project."""
    print("Available functions:")
    for name, func in functions.items():
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
