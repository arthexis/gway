import os
import re
import sys
import time
import inspect
import logging
import pathlib
import argparse
import unittest
import functools
import importlib.util

from .logging import setup_logging
from .builtins import abort, print
from .structs import Results


logger = logging.getLogger(__name__)


BASE_PATH = os.path.dirname(os.path.dirname(__file__))
LIBRARY_MODE = True


def load_project(project_name: str, root: str = None) -> tuple:
    if root is None:
        root = os.path.join(BASE_PATH, "projects")

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
    _first_root = None

    def __init__(self, root=None, **kwargs):
        if root is None:
            root = Gateway._first_root
            if root is None:
                root = BASE_PATH  # Default to the base path if no root is set
                Gateway._first_root = root  # first time, set default

        if not os.path.isdir(root):
            abort(f"Invalid project root: {root}")

        self.root = root
        self._cache = {}
        self.results = Results()
        self.builtin = type("builtin", (), {})()
        self.context = {**kwargs}  # Used to pass arguments between function calls
        self.used_context = []  # To track which keys were used
        self._load_builtins()

        # Add logging
        self.logger = logging.getLogger(__name__)

    def _load_builtins(self):
        """Load built-in functions and install them in the Gateway instance."""
        # Show a warning if a builtin overrides an existing gateway attribute
        builtins_functions = load_builtins()
        for name, func in builtins_functions.items():
            if hasattr(self, name):
                self.logger.warning(f"Builtin function '{name}' overrides existing Gateway attribute.")
            wrapped_func = self._wrap_callable(name, func)
            setattr(self.builtin, name, wrapped_func)
            setattr(self, name, wrapped_func)  # Install directly on self

    def resolve(self, value: str, param_name: str = None) -> str:
        """Resolve [key|fallback], [key], or [|fallback] sigils within a string."""
        if not isinstance(value, str):
            return value

        # Regex matches [key|fallback], [key], or [|fallback]
        sigil_pattern = r"\[([^|\[\]]*?)\|([^|\[\]]*?)\]|\[([^\[\]|]+)\]"

        def replacer(match):
            if match.group(1) is not None and match.group(2) is not None:
                key = match.group(1).strip() or (param_name or "")
                fallback = match.group(2).strip() or None
            elif match.group(3) is not None:
                key = match.group(3).strip()
                fallback = None
            else:
                return None  # malformed sigil

            resolved = self._resolve_key(key, fallback, param_name)
            return str(resolved) if resolved is not None else ""

        # Substitute all matches
        result = re.sub(sigil_pattern, replacer, value)

        return result if result != "" else None

    def _resolve_key(self, key: str, fallback: str = None, param_name: str = None) -> str:
        """Helper method to resolve a key from results, context, or environment vars."""
        search_keys = [key, key.lower(), key.upper()]

        for k in search_keys:
            if k in self.results:
                self.used_context.append(k)
                return self.results[k]
            if k in self.context:
                self.used_context.append(k)
                return self.context[k]
            env_val = os.getenv(k.upper())
            if env_val is not None:
                return env_val

        # If nothing found and fallback is provided, return fallback
        return fallback
            
    def _wrap_callable(self, func_name, func_obj):
        @functools.wraps(func_obj)
        def wrapped(*args, **kwargs):
            try:
                self.logger.debug(f"Calling {func_name} with args: {args} and kwargs: {kwargs}")

                # Get the function signature
                sig = inspect.signature(func_obj)
                bound_args = sig.bind_partial(*args, **kwargs)
                bound_args.apply_defaults()

                self.logger.debug(f"Context before argument injection: {self.context}")

                # First fill missing args from context (only those required by the function)
                for param in sig.parameters.values():
                    if param.name not in bound_args.arguments:
                        default_value = param.default
                        if isinstance(default_value, str) and default_value.startswith("[") and default_value.endswith("]"):
                            resolved = self.resolve(default_value, param_name=param.name)
                            bound_args.arguments[param.name] = resolved
                            self.used_context.append(param.name)  # Track the used context

                # Then resolve all [|...] inside provided args as well
                for key, value in bound_args.arguments.items():
                    if isinstance(value, str):
                        bound_args.arguments[key] = self.resolve(value, param_name=key)

                    # Update context always
                    self.context[key] = bound_args.arguments[key]

                self.logger.debug(f"Bound args for {func_name}: {bound_args.arguments}")
                final_args = {key: bound_args.arguments[key] for key in bound_args.arguments if key in sig.parameters}
                result = func_obj(**final_args)  

                self.results.insert(func_name, result)

                if isinstance(result, dict):
                    self.context.update(result)

                return result
            except Exception as e:
                print(f"Error while executing '{func_name}': {e}")
                raise
        return wrapped

    def __getattr__(self, project_name):
        if project_name in self._cache:
            return self._cache[project_name]

        try:
            module, functions = load_project(project_name, self.root)
            project_obj = type(project_name, (), {})()
            for func_name, func_obj in functions.items():
                wrapped_func = self._wrap_callable(f"{project_name}.{func_name}", func_obj)
                setattr(project_obj, func_name, wrapped_func)
            self._cache[project_name] = project_obj
            return project_obj
        except Exception as e:
            raise AttributeError(f"Project '{project_name}' not found: {e}")
        
    def __hasattr__(self, project_name):
        try:
            _ = self.__getattr__(project_name)
            return True
        except AttributeError:
            return False

    def resource(self, *parts, make_dirs=True, touch=False, is_dir=False, is_file=False, root=None):
        """Construct a path relative to the root and optionally prepare it."""
        # Should be safe to create dirs by default as they won't be persisted in the repo if empty
        path = pathlib.Path(root or self.root, *parts)
        if make_dirs:
            # Only create directories if they don't already exist
            if is_file or touch:
                if not path.parent.exists():
                    path.parent.mkdir(parents=True, exist_ok=True)
            else:
                if not path.exists():
                    path.mkdir(parents=True, exist_ok=True)
        if touch:
            if not path.exists():
                path.touch()
        if is_dir:
            if not path.is_dir():
                raise FileNotFoundError(f"Expected directory at: {path}")
        if is_file:
            if not path.is_file():
                raise FileNotFoundError(f"Expected file at: {path}")
        return path


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


def add_function_args(subparser, func_obj):
    """Add the function arguments to the subparser."""
    for arg_name, param in inspect.signature(func_obj).parameters.items():
        arg_name_cli = f"--{arg_name.replace('_', '-')}"
        if param.annotation == bool or isinstance(param.default, bool):
            group = subparser.add_mutually_exclusive_group(required=False)
            group.add_argument(arg_name_cli, dest=arg_name, action="store_true", help=f"Enable {arg_name}")
            group.add_argument(f"--no-{arg_name.replace('_', '-')}", dest=arg_name, action="store_false", help=f"Disable {arg_name}")
            subparser.set_defaults(**{arg_name: param.default})
        else:
            arg_opts = {
                "type": param.annotation if param.annotation != inspect.Parameter.empty else str
            }
            if param.default != inspect.Parameter.empty:
                arg_opts["default"] = param.default
            else:
                arg_opts["required"] = True
            subparser.add_argument(arg_name_cli, **arg_opts)


def load_env(env_type: str, name: str, env_root: str):
    """
    Load environment variables from envs/{clients|servers}/{name}.env
    If the file doesn't exist, create an empty one and log a warning.
    Ensures the .env filename is always lowercase.
    """
    assert env_type in ("clients", "servers"), "env_type must be 'clients' or 'servers'"
    env_dir = os.path.join(env_root, env_type)
    os.makedirs(env_dir, exist_ok=True)  # Create folder structure if needed

    # Ensure the name is lowercase for the filename
    env_file = os.path.join(env_dir, f"{name.lower()}.env")

    if not os.path.isfile(env_file):
        # Create empty .env file
        open(env_file, "a").close()
        logger.warning(f"{env_type.capitalize()} env file '{env_file}' not found. Created an empty one.")
        return

    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue  # Skip comments and empty lines
            if "=" in line:
                key, value = line.split("=", 1)
                os.environ[key.strip()] = value.strip()
                logger.debug(f"Loaded env var: {key.strip()}={value.strip()}")


def get_default_client():
    """Get the default client name based on logged in username."""
    try:
        import getpass
        username = getpass.getuser()
        return username if username else "guest"
    except Exception:
        return "guest"
    

def get_default_server():
    """Get the default server name based on machine hostname."""
    try:
        import socket
        hostname = socket.gethostname()
        return hostname if hostname else "localhost"
    except Exception:
        return "localhost"
    

def cli_main():
    """Main CLI entry point with function chaining support."""
    global LIBRARY_MODE
    LIBRARY_MODE = False  

    parser = argparse.ArgumentParser(description="Dynamic Project CLI")
    parser.add_argument("-r", "--root", type=str, help="Specify project directory")
    parser.add_argument("-t", "--timed", action="store_true", help="Enable timing")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("-c", "--client", type=str, help="Specify client environment")
    parser.add_argument("-s", "--server", type=str, help="Specify server environment")
    parser.add_argument("commands", nargs=argparse.REMAINDER, help="Project/Function command(s)")

    args = parser.parse_args()

    loglevel = "DEBUG" if args.debug else "INFO"
    setup_logging(logfile="gway.log", loglevel=loglevel, app_name="gway")

    START_TIME = time.time() if args.timed else None

    if not args.commands:
        parser.print_help()
        sys.exit(1)

    env_root = os.path.join(args.root or BASE_PATH, "envs")

    # Load environments
    client_name = args.client or get_default_client()
    load_env("clients", client_name, env_root)

    if args.commands[0] == "test":
        print("Running the test suite...")
        os.environ['TEST_MODE'] = '1'
        test_loader = unittest.TestLoader()
        test_suite = test_loader.discover('tests')
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(test_suite)
        sys.exit(0 if result.wasSuccessful() else 1)

    server_name = args.server or get_default_server()
    load_env("servers", server_name, env_root)
    gway_root = os.environ.get("GWAY_ROOT", args.root or BASE_PATH)

    # Split command chains
    command_line = " ".join(args.commands)
    command_chunks = command_line.split(" - ") if " - " in command_line else command_line.split(";")

    gway = Gateway(root=gway_root)
    current_project_obj = None
    last_result = None

    for chunk in command_chunks:
        chunk = chunk.strip()
        if not chunk:
            continue

        tokens = chunk.split()
        if not tokens:
            continue

        raw_first_token = tokens[0]
        normalized_first_token = raw_first_token.replace("-", "_")
        remaining_tokens = tokens[1:]

        # Resolve project or builtin
        try:
            current_project_obj = getattr(gway, normalized_first_token)
            if callable(current_project_obj):
                func_obj = current_project_obj
                func_tokens = [raw_first_token] + remaining_tokens
                project_functions = {raw_first_token: func_obj}
            else:
                project_functions = {
                    name: func for name, func in vars(current_project_obj).items()
                    if callable(func) and not name.startswith("_")
                }
                if not remaining_tokens:
                    show_functions(project_functions)
                    sys.exit(0)
                func_tokens = remaining_tokens
        except AttributeError:
            try:
                func_obj = getattr(gway.builtin, normalized_first_token)
                if callable(func_obj):
                    project_functions = {raw_first_token: func_obj}
                    func_tokens = [raw_first_token] + remaining_tokens
                else:
                    abort(f"Unknown command or project: {raw_first_token}")
            except AttributeError:
                if current_project_obj:
                    project_functions = {
                        name: func for name, func in vars(current_project_obj).items()
                        if callable(func) and not name.startswith("_")
                    }
                    func_tokens = [raw_first_token] + remaining_tokens
                else:
                    abort(f"Unknown project, builtin, or function: {raw_first_token}")

        if not func_tokens:
            abort(f"No function specified for project or builtin '{raw_first_token}'")

        raw_func_name = func_tokens[0]
        normalized_func_name = raw_func_name.replace("-", "_")
        func_args = func_tokens[1:]

        func_obj = project_functions.get(raw_func_name) or project_functions.get(normalized_func_name)
        if not func_obj:
            abort(f"Function '{raw_func_name}' not found.")

        func_parser = argparse.ArgumentParser(prog=raw_func_name)
        add_function_args(func_parser, func_obj)
        parsed_args = func_parser.parse_args(func_args)

        func_kwargs = {
            k: v for k, v in vars(parsed_args).items()
            if k in inspect.signature(func_obj).parameters
        }

        try:
            last_result = func_obj(**func_kwargs)
        except Exception as e:
            abort(f"Error executing '{raw_func_name}': {e}")

    if last_result is not None:
        gway.print(last_result)

    if START_TIME:
        elapsed_time = time.time() - START_TIME
        print(f"Elapsed: {elapsed_time:.4f} seconds")
