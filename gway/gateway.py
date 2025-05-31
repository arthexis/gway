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
from types import SimpleNamespace
from .sigils import Resolver
from .structs import Results

class ProjectStub(SimpleNamespace):
    def __init__(self, name, funcs, gateway):
        """
        A stub representing a project namespace. Holds available functions
        and raises an error when called without an explicit function.
        """
        super().__init__(**funcs)
        self._gateway = gateway
        self._name = name
        # _default_func is no longer used for guessing
        self._default_func = None

    def __call__(self, *args, **kwargs):
        """
        When the project object itself is invoked, list all available
        functions and abort with an informative error, instead of guessing.
        """
        from gway.console import show_functions

        # Gather all callables in this namespace
        functions = {
            name: func
            for name, func in self.__dict__.items()
            if callable(func)
        }

        # Display available functions to the user
        show_functions(functions)

        # Abort with a clear message
        gw.abort(f"Invalid function specified for project '{self._name}'")

class Gateway(Resolver):
    _builtin_cache = None
    _thread_local = threading.local()

    def __init__(self, *, verbose=False, name="gw", _debug=False, **kwargs):

        self._cache = {}
        self._async_threads = []
        self._debug = _debug
        self.uuid = uuid.uuid4()
        self.base_path = os.path.dirname(os.path.dirname(__file__))
        self.name = name
        self.logger = logging.getLogger(name)
        if not verbose:
            self.verbose =  lambda *_, **__: None
        elif verbose is True:
            self.verbose =  lambda *args, **kwargs: self.info(*args, **kwargs)

        if not hasattr(Gateway._thread_local, "context"):
            Gateway._thread_local.context = {}
        if not hasattr(Gateway._thread_local, "results"):
            Gateway._thread_local.results = Results()

        Gateway._thread_local.context.update(kwargs)

        self.context = Gateway._thread_local.context
        self.results = Gateway._thread_local.results

        super().__init__([
            ('results', self.results),
            ('context', self.context),
            ('env', os.environ),
        ])

        if Gateway._builtin_cache is None:
            builtins_module = importlib.import_module("gway.builtins")
            Gateway._builtin_cache = {
                name: obj for name, obj in inspect.getmembers(builtins_module)
                if inspect.isfunction(obj)
                and not name.startswith("_")
                and inspect.getmodule(obj) == builtins_module
            }

        self._builtin_functions = Gateway._builtin_cache.copy()

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

                for param in sig.parameters.values():
                    if (param.name not in bound_args.arguments
                        and param.kind not in (param.VAR_POSITIONAL, param.VAR_KEYWORD)):
                        default_value = param.default
                        if (isinstance(default_value, str)
                            and default_value.startswith("[")
                            and default_value.endswith("]")):
                            bound_args.arguments[param.name] = self.resolve(default_value)

                for key, value in bound_args.arguments.items():
                    if isinstance(value, str):
                        bound_args.arguments[key] = self.resolve(value)
                    self.context[key] = bound_args.arguments[key]

                args_to_pass = []
                kwargs_to_pass = {}
                for param in sig.parameters.values():
                    if param.kind == param.VAR_POSITIONAL:
                        args_to_pass.extend(bound_args.arguments.get(param.name, ()))
                    elif param.kind == param.VAR_KEYWORD:
                        kwargs_to_pass.update(bound_args.arguments.get(param.name, {}))
                    elif param.name in bound_args.arguments:
                        val = bound_args.arguments[param.name]
                        if param.default == val:
                            found = self.find_value(param.name)
                            if found is not None and found != val:
                                self.info(f"Injected {param.name}={found} overrides default {val=}")
                                val = found
                        kwargs_to_pass[param.name] = val

                if inspect.iscoroutinefunction(func_obj):
                    thread = threading.Thread(
                        target=self._run_coroutine,
                        args=(func_name, func_obj, args_to_pass, kwargs_to_pass),
                        daemon=True
                    )
                    self._async_threads.append(thread)
                    thread.start()
                    return f"[async task started for {func_name}]"

                result = func_obj(*args_to_pass, **kwargs_to_pass)

                if inspect.iscoroutine(result):
                    thread = threading.Thread(
                        target=self._run_coroutine,
                        args=(func_name, result),
                        daemon=True
                    )
                    self._async_threads.append(thread)
                    thread.start()
                    return f"[async coroutine started for {func_name}]"

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

                    self.info(f"Stored {result=} into {sk=} {lk=}")
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
            ns = ProjectStub(dotted, funcs, self)
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
                funcs[subname] = ProjectStub(dotted, sub_funcs, self)
            elif os.path.isdir(full) and not entry.startswith("__"):
                dotted = f"{dotted_prefix}.{entry}"
                funcs[entry] = self.recurse_namespace(full, dotted)
        ns = ProjectStub(dotted_prefix, funcs, self)
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
