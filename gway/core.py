import os
import re
import sys
import time
import inspect
import logging
import argparse
import unittest
import functools
import importlib.util

from .logging import setup_logging
from .builtins import abort, print, verbose
from .structs import Results


logger = logging.getLogger(__name__)


def load_project(project_name: str, root: str = None) -> tuple:
    if root is None:
        root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "projects")

    if not os.path.isdir(root):
        raise FileNotFoundError(f"Invalid project root: {root}")

    project_parts = project_name.split(".")
    project_file = os.path.join(root, *project_parts) + ".py"

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
    _default_root = None

    def __init__(self, root=None):
        if root is None:
            root = Gateway._default_root
            if root is None:
                root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "projects")
                Gateway._default_root = root  # first time, set default

        if not os.path.isdir(root):
            abort(f"Invalid project root: {root}")

        self.root = root
        self._cache = {}
        self.results = Results()
        self.builtin = type("builtin", (), {})()
        self.context = {}  # Used to pass arguments between function calls
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
        """Resolve [key|fallback] sigils anywhere within the string."""
        if not isinstance(value, str):
            return value
        
        # Pattern to match [key|fallback] inside the string
        sigil_pattern = r"\[([^\[\]]+)\|([^\[\]]+)\]|\[([^\[\]]+)\]"
        matches = re.finditer(sigil_pattern, value)

        # For each match, resolve the key or fallback
        for match in matches:
            if match.group(1) and match.group(2):  # has both key and fallback
                key, fallback = match.group(1).strip(), match.group(2).strip()
            else:  # only a key (fallback is empty, use param_name dynamically)
                key = match.group(3).strip()
                # If fallback is empty, use the param_name as a key dynamically
                fallback = param_name

            resolved_value = self._resolve_key(key, fallback, param_name)
            value = value.replace(match.group(0), str(resolved_value))

        return value

    def _resolve_key(self, key: str, fallback: str, param_name: str) -> str:
        """Helper method to resolve a key from context, results, or environment variables."""
        search_keys = [key, key.lower(), key.upper()]

        # If the fallback is a param_name, use the context with the param_name dynamically
        if fallback == param_name and param_name in self.context:
            self.used_context.append(param_name)  # Track usage
            return self.context[param_name]

        # Search in context, results, or environment variables
        for k in search_keys:
            if k in self.context:
                self.used_context.append(k)  # Track usage
                return self.context[k]
            if k in self.results:
                return self.results[k]
            env_val = os.getenv(k.upper())
            if env_val is not None:
                return env_val

        return fallback if fallback is not None else key
    
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

    parser = argparse.ArgumentParser(description="Dynamic Project CLI")
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")
    parser.add_argument("-r", "--root", type=str, help="Specify project directory")
    parser.add_argument("-t", "--timed", action="store_true", help="Enable timing")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("-c", "--client", type=str, help="Specify client environment")
    parser.add_argument("-s", "--server", type=str, help="Specify server environment")
    parser.add_argument("commands", nargs=argparse.REMAINDER, help="Project/Function command(s)")

    args = parser.parse_args()

    if args.verbose:
        verbose(True)

    loglevel = "DEBUG" if args.debug else "INFO"
    setup_logging(logfile="gway.log", loglevel=loglevel, app_name="gway")

    START_TIME = time.time() if args.timed else None

    if not args.commands:
        parser.print_help()
        sys.exit(1)

    env_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), "envs")

    # Handle client env loading
    client_name = args.client or get_default_client()
    load_env("clients", client_name, env_root)

    # If the project is "test", run the tests using unittest
    if args.commands[0] == "test":
        print("Running the test suite...")
        os.environ['TEST_MODE'] = '1'
        test_loader = unittest.TestLoader()
        test_suite = test_loader.discover('tests')
        runner = unittest.TextTestRunner(verbosity=2)
        result = runner.run(test_suite)
        sys.exit(0 if result.wasSuccessful() else 1)

    # Handle server env loading
    server_name = args.server or get_default_server()
    load_env("servers", server_name, env_root)
    
    # Join the commands list back to a single string
    command_line = " ".join(args.commands)

    # Split based on " - " or ";"
    if " - " in command_line:
        command_chunks = command_line.split(" - ")
    else:
        command_chunks = command_line.split(";")

    gway = Gateway(root=args.root)

    current_project_obj = None

    for chunk in command_chunks:
        chunk = chunk.strip()
        if not chunk:
            continue

        tokens = chunk.split()
        if not tokens:
            continue

        first_token = tokens[0]
        remaining_tokens = tokens[1:]

        # Convert dashes to underscores
        first_token = first_token.replace("-", "_")
        remaining_tokens = tokens[1:] 

        # Determine if first token is a project, builtin, or function
        try:
            # Try loading project
            current_project_obj = getattr(gway, first_token)
            if callable(current_project_obj):
                # It's a builtin function
                func_obj = current_project_obj
                func_tokens = [first_token] + remaining_tokens
                project_functions = {first_token: func_obj}
            else:
                # It's a project object
                project_functions = {
                    name: func for name, func in vars(current_project_obj).items()
                    if callable(func) and not name.startswith("_")
                }
                if not remaining_tokens:
                    show_functions(project_functions)
                    sys.exit(0)
                func_tokens = remaining_tokens
        except AttributeError:
            # Maybe it's a builtin function
            try:
                func_obj = getattr(gway.builtin, first_token)
                if callable(func_obj):
                    project_functions = {first_token: func_obj}
                    func_tokens = [first_token] + remaining_tokens
                else:
                    abort(f"Unknown command or project: {first_token}")
            except AttributeError:
                # Try treating it as function of current project
                if current_project_obj:
                    project_functions = {
                        name: func for name, func in vars(current_project_obj).items()
                        if callable(func) and not name.startswith("_")
                    }
                    func_tokens = [first_token] + remaining_tokens
                else:
                    abort(f"Unknown project, builtin, or function: {first_token}")

        if not func_tokens:
            abort(f"No function specified for project or builtin '{first_token}'")

        func_name = func_tokens[0]
        func_args = func_tokens[1:]

        func_obj = project_functions.get(func_name)
        if not func_obj:
            abort(f"Function '{func_name}' not found.")

        func_parser = argparse.ArgumentParser(prog=func_name)
        add_function_args(func_parser, func_obj)
        parsed_args = func_parser.parse_args(func_args)

        func_kwargs = {
            k: v for k, v in vars(parsed_args).items()
            if k in inspect.signature(func_obj).parameters
        }

        try:
            func_obj(**func_kwargs)
        except Exception as e:
            abort(f"Error executing '{func_name}': {e}")

    if START_TIME:
        elapsed_time = time.time() - START_TIME
        print(f"Elapsed: {elapsed_time:.4f} seconds")
