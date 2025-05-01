import os
import importlib
import inspect


def load_project(project_name: str, root: str) -> tuple:
    # Only load functions that are explicitly declared in the imported module
    # Avoid including functions that were imported from somewhere else to avoid duplication
    if not os.path.isdir(root):
        raise FileNotFoundError(f"Invalid project root: {root}")

    project_parts = project_name.split(".")
    project_file = os.path.join(root, "projects", *project_parts) + ".py"

    if not os.path.isfile(project_file):
        raise FileNotFoundError(f"Project file '{project_file}' not found.")

    module_name = project_name.replace(".", "_")
    spec = importlib.util.spec_from_file_location(module_name, project_file)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load spec for {project_name}")

    project_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(project_module)

    project_functions = {
        name: obj for name, obj in inspect.getmembers(project_module, inspect.isfunction)
        if not name.startswith("_") and obj.__module__ == project_module.__name__
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
