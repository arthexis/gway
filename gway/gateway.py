import os
import time
import inspect
import logging
import asyncio
import threading
import functools

from .functions import load_builtins, load_project
from .sigils import Resolver
from .structs import Results


class Gateway(Resolver):
    _builtin_cache = None

    def __init__(self, **kwargs):
        self._cache = {}
        self._async_threads = []
        self.base_path = os.path.dirname(os.path.dirname(__file__))
        self.results = Results()
        self.context = {**kwargs}
        self.logger = logging.getLogger("gw")

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
                self.debug(f"Call <{func_name}>: {args=} {kwargs=}")
                sig = inspect.signature(func_obj)
                bound_args = sig.bind_partial(*args, **kwargs)
                bound_args.apply_defaults()
                # self.debug(f"Context before argument injection: {self.context}")

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
                self.error(f"Error in '{func_name}': {e}")
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
            self.error(f"Async error in {func_name}: {e}")
        finally:
            loop.close()

    def hold(self, lock_file=None, lock_url=None, lock_pypi=False):
        from .watchers import watch_file, watch_url, watch_pypi_package
        # TODO: Create a PID watcher and allow hold to use it with a lock_pid kwarg.
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
            self.warning("KeyboardInterrupt received. Exiting immediately.")
            os._exit(1)

    def __getattr__(self, name):
        # Delegate standard logger methods to self.logger
        if hasattr(self.logger, name) and callable(getattr(self.logger, name)):
            return getattr(self.logger, name)

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
            self.debug(f"Loading project {name}")
            _, functions = load_project(self.base_path, name)
            project_obj = type(name, (), {})()
            for func_name, func_obj in functions.items():
                wrapped_func = self._wrap_callable(f"{name}.{func_name}", func_obj)
                setattr(project_obj, func_name, wrapped_func)
            self._cache[name] = project_obj
            return project_obj
        except Exception as e:
            raise AttributeError(f"Project or builtin '{name}' not found: {e}")


gw = Gateway()

