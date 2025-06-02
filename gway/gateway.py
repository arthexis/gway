# gway/gateway.py

import os
import re
import sys
import time
import uuid
import inspect
import logging
import asyncio
import threading
import importlib
import functools

from .envs import load_env, get_base_client, get_base_server
from .sigils import Resolver
from .structs import Results, Project


class Gateway(Resolver):
    _builtins = None
    _thread_local = threading.local()

    # TODO: Store all available projects in self._projects
    # Then create a method to list them called projects()
    # Similarly, create a method builtins() to list all available builtins

    def __init__(self, *, 
                client=None, server=None, verbose=False, 
                name="gw", _debug=False, **kwargs
    ):
        # Basic initialization
        self._cache = {}
        self._async_threads = []
        self._debug = _debug
        self._projects = []
        self.uuid = uuid.uuid4()
        self.base_path = os.path.dirname(os.path.dirname(__file__))
        self.name = name
        self.logger = logging.getLogger(name)

        if not verbose:
            self.verbose = lambda *_, **__: None
        elif verbose is True:
            self.verbose = lambda *args, **kwargs: self.info(*args, **kwargs)

        # Pull out client/server overrides so they don't go into context
        client_name = client or get_base_client()
        server_name = server or get_base_server()

        # Ensure thread-local context/results exist
        if not hasattr(Gateway._thread_local, "context"):
            Gateway._thread_local.context = {}
        if not hasattr(Gateway._thread_local, "results"):
            Gateway._thread_local.results = Results()

        # Merge any extra kwargs into the shared context
        Gateway._thread_local.context.update(kwargs)

        self.context = Gateway._thread_local.context
        self.results = Gateway._thread_local.results

        # Initialize the Resolver with "results", "context", and the real OS environment
        super().__init__([
            ('results', self.results),
            ('context', self.context),
            ('env', os.environ),
        ])

        # === Moved load_env here so every Gateway always loads env correctly ===
        env_root = os.path.join(self.base_path, "envs")
        load_env("client", client_name, env_root)
        load_env("server", server_name, env_root)

        # Populate the builtin-function cache on first instantiation
        if Gateway._builtins is None:
            builtins_module = importlib.import_module("gway.builtins")
            Gateway._builtins = {
                name: obj
                for name, obj in inspect.getmembers(builtins_module)
                if inspect.isfunction(obj)
                and not name.startswith("_")
                and inspect.getmodule(obj) == builtins_module
            }

        self._builtin_functions = Gateway._builtins.copy()

    def projects(self):
        return sorted(self._projects)

    def builtins(self):
        return sorted(self._builtins)

    def success(self, message):
        print(message)
        self.info(message)

    def _wrap_callable(self, func_name, func_obj):
        @functools.wraps(func_obj)
        def wrapped(*args, **kwargs):
            try:
                self.debug(f"Call <{func_name}>: {args=} {kwargs=}")
                sig = inspect.signature(func_obj)
                bound_args = sig.bind_partial(*args, **kwargs)
                bound_args.apply_defaults()

                # Resolve “[...]” placeholder defaults from context
                for param in sig.parameters.values():
                    if (param.name not in bound_args.arguments
                        and param.kind not in (param.VAR_POSITIONAL, param.VAR_KEYWORD)):
                        default_value = param.default
                        if (isinstance(default_value, str)
                            and default_value.startswith("[")
                            and default_value.endswith("]")):
                            bound_args.arguments[param.name] = self.resolve(default_value)

                # Resolve any string arguments via self.resolve, and inject into context
                for key, value in bound_args.arguments.items():
                    if isinstance(value, str):
                        bound_args.arguments[key] = self.resolve(value)
                    self.context[key] = bound_args.arguments[key]

                # Separate positional vs keyword for final call
                args_to_pass = []
                kwargs_to_pass = {}
                for param in sig.parameters.values():
                    if param.kind == param.VAR_POSITIONAL:
                        args_to_pass.extend(bound_args.arguments.get(param.name, ()))
                    elif param.kind == param.VAR_KEYWORD:
                        kwargs_to_pass.update(bound_args.arguments.get(param.name, {}))
                    elif param.name in bound_args.arguments:
                        val = bound_args.arguments[param.name]
                        # If the argument still equals its default, try to override from context
                        if param.default == val:
                            found = self.find_value(param.name)
                            if found is not None and found != val:
                                self.info(f"Injected {param.name}={found} overrides default {val=}")
                                val = found
                        kwargs_to_pass[param.name] = val

                # If function is async, start thread to run it
                if inspect.iscoroutinefunction(func_obj):
                    thread = threading.Thread(
                        target=self._run_coroutine,
                        args=(func_name, func_obj, args_to_pass, kwargs_to_pass),
                        daemon=True
                    )
                    self._async_threads.append(thread)
                    thread.start()
                    return f"[async task started for {func_name}]"

                # Call the function synchronously
                result = func_obj(*args_to_pass, **kwargs_to_pass)

                # If it returns a coroutine, run that in a thread
                if inspect.iscoroutine(result):
                    thread = threading.Thread(
                        target=self._run_coroutine,
                        args=(func_name, result),
                        daemon=True
                    )
                    self._async_threads.append(thread)
                    thread.start()
                    return f"[async coroutine started for {func_name}]"

                # At this point, `result` is a concrete return value
                if result is not None:
                    parts = func_name.split(".")
                    project = parts[-2] if len(parts) > 1 else parts[-1]
                    func = parts[-1]

                    def split_words(name):
                        return re.findall(r'[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)', name.replace("_", " "))

                    words = split_words(func)
                    if len(words) == 1:
                        sk = project
                    else:
                        sk = words[-1]

                    lk = ".".join([project] + words[1:]) if len(words) > 1 else project

                    # — if the repr of result is very long, truncate it —
                    repr_result = repr(result)
                    if len(repr_result) > 100:
                        short_result = repr_result[:100] + "...[truncated]"
                    else:
                        short_result = repr_result

                    # — if the storage key looks sensitive, censor it —
                    sensitive_keywords = ("password", "secret", "token", "key")
                    if any(word.lower() in sk.lower() for word in sensitive_keywords):
                        log_value = "<censored>"
                    else:
                        log_value = short_result

                    self.info(f"Stored result={log_value} into sk={sk} lk={lk}")
                    self.results.insert(sk, result)
                    if lk != sk:
                        self.results.insert(lk, result)
                    if isinstance(result, dict):
                        self.context.update(result)
                else:
                    self.debug("Result is None, skip storing.")

                return result

            except Exception as e:
                self.error(f"Error in '{func_name}': {e}")
                raise

        return wrapped

    def _run_coroutine(self, func_name, coro_or_func, args=None, kwargs=None):
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            if asyncio.iscoroutine(coro_or_func):
                result = loop.run_until_complete(coro_or_func)
            else:
                result = loop.run_until_complete(coro_or_func(*(args or ()), **(kwargs or {})))

            self.results.insert(func_name, result)
            if isinstance(result, dict):
                self.context.update(result)
        except Exception as e:
            self.error(f"Async error in {func_name}: {e}")
            self.exception(e)
        finally:
            loop.close()

    def until(self, *, lock_file=None, lock_url=None, lock_pypi=False):
        from .watchers import watch_file, watch_url, watch_pypi_package
        def shutdown(reason):
            self.warning(f"{reason} triggered async shutdown.")
            os._exit(1)

        watchers = [
            (lock_file, watch_file, "Lock file"),
            (lock_url, watch_url, "Lock url"),
            (lock_pypi if lock_pypi is not False else None, watch_pypi_package, "PyPI package")
        ]
        for target, watcher, reason in watchers:
            if target:
                self.info(f"Setup watcher for {reason}")
                if target is True and lock_pypi:
                    target = "gway"
                watcher(target, on_change=lambda r=reason: shutdown(r))
        try:
            while any(thread.is_alive() for thread in self._async_threads):
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.critical("KeyboardInterrupt received. Exiting immediately.")
            os._exit(1)

    def __getattr__(self, name):
        if hasattr(self.logger, name) and callable(getattr(self.logger, name)):
            return getattr(self.logger, name)

        if name in self._builtin_functions:
            func = self._wrap_callable(name, self._builtin_functions[name])
            setattr(self, name, func)
            return func

        if name in self._cache: return self._cache[name]

        try:
            project_obj = self.load_project(project_name=name)
            return project_obj
        except Exception as e:
            raise AttributeError(f"Project or builtin '{name}' not found: {e}")

    def load_project(self, project_name: str, *, root: str = "projects"):
        base = gw.resource(root, *project_name.split("."))
        self.debug(f"Loading {project_name} from {base}")

        def load_module_namespace(py_path: str, dotted: str):
            mod = self.load_py_file(py_path, dotted)
            funcs = {}
            for fname, obj in inspect.getmembers(mod, inspect.isfunction):
                if not fname.startswith("_"):
                    funcs[fname] = self._wrap_callable(f"{dotted}.{fname}", obj)
            ns = Project(dotted, funcs, self)
            self._cache[dotted] = ns
            return ns

        if os.path.isdir(base):
            return self.recurse_namespace(base, project_name)

        from pathlib import Path
        base_path = Path(base)
        py_file = base_path if base_path.suffix == ".py" else base_path.with_suffix(".py")
        if py_file.is_file():
            return load_module_namespace(str(py_file), project_name)

        raise FileNotFoundError(f"Project path not found: {base}")

    def load_py_file(self, path: str, dotted_name: str):
        module_name = dotted_name.replace(".", "_")
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load spec for {path}")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = mod
        try:
            spec.loader.exec_module(mod)
        except Exception:
            self.error(f"Failed to import {dotted_name} from {path}", exc_info=True)
            raise
        return mod

    def recurse_namespace(self, current_path: str, dotted_prefix: str):
        funcs = {}
        for entry in os.listdir(current_path):
            full = os.path.join(current_path, entry)
            if entry.endswith(".py") and not entry.startswith("__"):
                subname = entry[:-3]
                dotted = f"{dotted_prefix}.{subname}"
                mod = self.load_py_file(full, dotted)
                sub_funcs = {}
                for fname, obj in inspect.getmembers(mod, inspect.isfunction):
                    if not fname.startswith("_"):
                        sub_funcs[fname] = self._wrap_callable(f"{dotted}.{fname}", obj)
                funcs[subname] = Project(dotted, sub_funcs, self)
            elif os.path.isdir(full) and not entry.startswith("__"):
                dotted = f"{dotted_prefix}.{entry}"
                funcs[entry] = self.recurse_namespace(full, dotted)
        ns = Project(dotted_prefix, funcs, self)
        self._cache[dotted_prefix] = ns
        return ns
    
    @property
    def debug_mode(self):
        return bool(self._debug)

    def log(self, *args, **kwargs):
        if self.debug_mode:
            self.debug(*args, **kwargs)
            return "debug"
        self.info(*args, **kwargs)
        return "info"


# This line allows using "from gway import gw" everywhere else
gw = Gateway()
