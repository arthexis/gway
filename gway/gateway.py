import os
import sys
import time
import inspect
import logging
import asyncio
import argparse
import threading
import functools

from .logging import setup_logging
from .builtins import abort, print, run_tests, get_tag, watch_file
from .environs import get_base_client, get_base_server, load_env
from .functions import load_builtins, load_project, show_functions
from .sigils import Resolver
from .structs import Results


logger = logging.getLogger(__name__)
BASE_PATH = os.path.dirname(os.path.dirname(__file__))


class Gateway(Resolver):
    _first_root = None
    _builtin_cache = None

    def __init__(self, root=None, **kwargs):
        if root is None:
            root = Gateway._first_root or BASE_PATH
            Gateway._first_root = root

        if not os.path.isdir(root):
            abort(f"Invalid project root: {root}")

        self.root = root
        self._cache = {}
        self._async_threads = []
        self.results = Results()
        self.context = {**kwargs}
        self.logger = logging.getLogger("gway")

        # Initialize Resolver with search order
        super().__init__([
            ('results', self.results),
            ('context', self.context),
            ('env', os.environ)
        ])

        self._builtin_functions = {}
        self._load_builtins()

    def _load_builtins(self):
        if Gateway._builtin_cache is None:
            Gateway._builtin_cache = load_builtins()

        self._builtin_functions = Gateway._builtin_cache.copy()
            
    def _wrap_callable(self, func_name, func_obj):
        @functools.wraps(func_obj)
        def wrapped(*args, **kwargs):
            try:
                self.logger.debug(f"Call {func_name} with args: {args} and kwargs: {kwargs}")

                sig = inspect.signature(func_obj)
                bound_args = sig.bind_partial(*args, **kwargs)
                bound_args.apply_defaults()
                # self.logger.debug(f"Context before argument injection: {self.context}")

                for param in sig.parameters.values():
                    if param.name not in bound_args.arguments and param.kind not in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
                        default_value = param.default
                        if isinstance(default_value, str) and default_value.startswith("[") and default_value.endswith("]"):
                            resolved = self.resolve(default_value)
                            bound_args.arguments[param.name] = resolved

                # Resolve and update context
                for key, value in bound_args.arguments.items():
                    if isinstance(value, str):
                        bound_args.arguments[key] = self.resolve(value)
                    self.context[key] = bound_args.arguments[key]

                # Prepare args and kwargs for function call
                args_to_pass = []
                kwargs_to_pass = {}
                for param in sig.parameters.values():
                    if param.kind == param.VAR_POSITIONAL:
                        args_to_pass.extend(bound_args.arguments.get(param.name, ()))
                    elif param.kind == param.VAR_KEYWORD:
                        kwargs_to_pass.update(bound_args.arguments.get(param.name, {}))
                    elif param.name in bound_args.arguments:
                        kwargs_to_pass[param.name] = bound_args.arguments[param.name]

                # Handle coroutine function
                if inspect.iscoroutinefunction(func_obj):
                    thread = threading.Thread(
                        target=self._run_coroutine,
                        args=(func_name, func_obj, args_to_pass, kwargs_to_pass),
                        daemon=True
                    )
                    self._async_threads.append(thread)
                    thread.start()
                    return f"[async task started for {func_name}]"

                # Call synchronous function
                result = func_obj(*args_to_pass, **kwargs_to_pass)

                # Handle coroutine result from sync function
                if inspect.iscoroutine(result):
                    thread = threading.Thread(
                        target=self._run_coroutine,
                        args=(func_name, result),
                        daemon=True
                    )
                    self._async_threads.append(thread)
                    thread.start()
                    return f"[async coroutine started for {func_name}]"

                # Store result
                short_key = func_name.split("_", 1)[-1] if "_" in func_name else func_name
                self.results.insert(short_key, result)
                if isinstance(result, dict):
                    self.context.update(result)

                return result

            except Exception as e:
                self.logger.error(f"Error in '{func_name}': {e}")
                raise

        return wrapped
        
    def _run_coroutine(self, func_name, coro_or_func, args=None, kwargs=None):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            # Determine if it's already a coroutine object
            if asyncio.iscoroutine(coro_or_func):
                result = loop.run_until_complete(coro_or_func)
            else:
                result = loop.run_until_complete(coro_or_func(*(args or ()), **(kwargs or {})))

            self.results.insert(func_name, result)
            if isinstance(result, dict):
                self.context.update(result)
        except Exception as e:
            self.logger.error(f"Async error in {func_name}: {e}")
        finally:
            loop.close()

    def hold(self, lock_file=None, lock_url=None, lock_pypi=False):
        def shutdown(reason):
            self.logger.warning(f"{reason} triggered async shutdown.")
            os._exit(1)

        watchers = [
            (lock_file, watch_file, "Lock file"),
            (lock_url, self.website.watch_url, "Lock url"),
            (lock_pypi if lock_pypi is not False else None,
            self.project.watch_pypi_package, "PyPI package")
        ]
        for target, watcher, reason in watchers:
            if target:
                self.logger.info(f"Setup watcher for {reason}")
                if target is True and lock_pypi:
                    target = "gway"
                watcher(target, on_change=lambda r=reason: shutdown(r), logger=self.logger)
        try:
            while any(thread.is_alive() for thread in self._async_threads):
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.logger.warning("KeyboardInterrupt received. Exiting immediately.")
            os._exit(1)

    def __getattr__(self, name):
        # Builtin function?
        if name in self._builtin_functions:
            func = self._wrap_callable(name, self._builtin_functions[name])
            setattr(self, name, func)
            return func

        # Cached project?
        if name in self._cache:
            return self._cache[name]

        # Try to load project
        try:
            module, functions = load_project(name, self.root)
            project_obj = type(name, (), {})()
            for func_name, func_obj in functions.items():
                wrapped_func = self._wrap_callable(f"{name}.{func_name}", func_obj)
                setattr(project_obj, func_name, wrapped_func)
            self._cache[name] = project_obj
            return project_obj
        except Exception as e:
            raise AttributeError(f"Project or builtin '{name}' not found: {e}")
        

def add_function_args(subparser, func_obj):
    """Add the function's arguments to the CLI subparser."""
    sig = inspect.signature(func_obj)
    logger.debug(f"Add function args for {func_obj.__name__} {sig}")
    resolver = Gateway()

    for arg_name, param in sig.parameters.items():
        logger.debug(f"Inspecting {arg_name=} {param=} {param.kind=}")
        if param.kind == inspect.Parameter.VAR_POSITIONAL:
            subparser.add_argument(arg_name, nargs='*', help=f"Variable positional arguments for {arg_name}")
        elif param.kind == inspect.Parameter.VAR_KEYWORD:
            subparser.add_argument('--kwargs', nargs='*', help='Additional keyword arguments as key=value pairs')
        else:
            arg_name_cli = f"--{arg_name.replace('_', '-')}"
            if param.annotation == bool or isinstance(param.default, bool):
                group = subparser.add_mutually_exclusive_group(required=False)
                group.add_argument(arg_name_cli, dest=arg_name, action="store_true", help=f"Enable {arg_name}")
                group.add_argument(f"--no-{arg_name.replace('_', '-')}", dest=arg_name, action="store_false", help=f"Disable {arg_name}")
                subparser.set_defaults(**{arg_name: param.default})
                logger.debug(f"Subparser default for {arg_name=} set to {param.default=}")
            else:
                arg_opts = {
                    "type": param.annotation if param.annotation != inspect.Parameter.empty else str
                }
                if param.default != inspect.Parameter.empty:
                    default_val = param.default
                    if isinstance(default_val, str) and default_val.startswith("[") and default_val.endswith("]"):
                        try:
                            default_val = resolver.resolve(default_val)
                        except Exception as e:
                            print(f"Warning: failed to resolve default for {arg_name}: {e}")
                    arg_opts["default"] = default_val
                else:
                    arg_opts["required"] = True
                subparser.add_argument(arg_name_cli, **arg_opts)
                logger.debug(f"Subparser {arg_name=} argument added as {arg_name_cli=} {arg_opts=}")


def chunk_command(args_commands):
    """Split args.commands into logical chunks without breaking quoted arguments."""
    chunks = []
    current_chunk = []

    for token in args_commands:
        if token in ('-', ';'):  # command separator
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
        else:
            current_chunk.append(token)

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


def cli_main():
    """Main CLI entry point with function chaining support."""

    parser = argparse.ArgumentParser(description="Dynamic Project CLI")
    parser.add_argument("-r", "--root", type=str, help="Specify project directory")
    parser.add_argument("-t", "--timed", action="store_true", help="Enable timing")
    parser.add_argument("-d", "--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("-c", "--client", type=str, help="Specify client environment")
    parser.add_argument("-s", "--server", type=str, help="Specify server environment")
    parser.add_argument("commands", nargs=argparse.REMAINDER, help="Project/Function command(s)")
    args = parser.parse_args()

    # TODO: Consider --all arg to return all results, not just the last one
    # TODO: Consider --json option to return last/all results as JSON (depending on --all)

    loglevel = "DEBUG" if args.debug else "INFO"
    setup_logging(logfile="gway.log", loglevel=loglevel, app_name="gway")
    logger.debug(f"Argparser first pass: {args}")
    start_time = time.time() if args.timed else None

    if not args.commands:
        parser.print_help()
        sys.exit(1)

    env_root = os.path.join(args.root or BASE_PATH, "envs")
    client_name = args.client or get_base_client()
    load_env("clients", client_name, env_root)

    if args.commands[0] == "test": 
        test_filter = args.commands[1] if len(args.commands) > 1 else None
        results = run_tests(filter=test_filter)
        sys.exit(0 if results else 1)

    server_name = args.server or get_base_server()
    load_env("servers", server_name, env_root)
    gway_root = os.environ.get("GWAY_ROOT", args.root or BASE_PATH)
    command_chunks = chunk_command(args.commands)

    gway = Gateway(root=gway_root)
    current_project_obj = None
    last_result = None

    for chunk in command_chunks:
        logger.debug(f"Processing chunk: {chunk}")
        if not chunk: continue

        raw_first_token = chunk[0]
        normalized_first_token = raw_first_token.replace("-", "_")
        remaining_tokens = chunk[1:]

        try:
            current_project_obj = getattr(gway, normalized_first_token)
            logger.debug(f"Matched gway attribute: {current_project_obj}")
            if callable(current_project_obj):
                func_obj = current_project_obj
                func_tokens = [raw_first_token] + remaining_tokens
                project_functions = {raw_first_token: func_obj}
                logger.debug(f"Element is callable {project_functions=}")
            else:
                project_functions = {
                    name: func for name, func in vars(current_project_obj).items()
                    if callable(func) and not name.startswith("_")
                }
                logger.debug(f"Element contents: {', '.join(project_functions.keys())}")
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
        logger.debug(f"Parsed {func_args=} into {parsed_args=}")

        func_kwargs = {}
        func_args = []
        extra_kwargs = {}

        for name, value in vars(parsed_args).items():
            param = inspect.signature(func_obj).parameters.get(name)
            if param is None:
                continue
            if param.kind == inspect.Parameter.VAR_POSITIONAL:
                func_args.extend(value or [])
            elif param.kind == inspect.Parameter.VAR_KEYWORD:
                if value:
                    for item in value:
                        if '=' not in item:
                            abort(f"Invalid kwarg format '{item}'. Expected key=value.")
                        k, v = item.split("=", 1)
                        extra_kwargs[k] = v
            else:
                func_kwargs[name] = value

        try:
            last_result = func_obj(*func_args, **{**func_kwargs, **extra_kwargs})
        except Exception as e:
            logger.error(e)
            abort(f"Unhandled {type(e).__name__} in {func_obj.__name__}")

    if last_result is not None:
        logger.info(f"Result:\n{last_result}") 
        gway.print(last_result)
    else:
        logger.warning(f"No results returned.")

    if start_time:
        elapsed_time = time.time() - start_time
        print(f"\nElapsed: {elapsed_time:.4f} seconds")

