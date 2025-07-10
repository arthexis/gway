# file: gway/gateway.py

import os
import sys
import uuid
import inspect
import logging
import threading
import importlib
import functools
import time
from pathlib import Path

from .envs import load_env, get_base_client, get_base_server
from .sigils import Resolver, Sigil, Spool
from .structs import Results, Project, Null
from .runner import Runner


class Gateway(Resolver, Runner):
    _builtins = None  # Class-level: stores all discovered builtins only once
    _thread_local = threading.local()
    defaults = {}

    Null = Null  # Null is a black-hole, assign with care.

    # Global state (typically set from CLI)
    debug = False
    silent = False
    verbose = False
    wizard = False
    timed = False

    def __init__(self, *,
                client=None, server=None, name="gw", base_path=None, project_path=None,
                verbose=None, silent=None, debug=None, wizard=None, timed=None, quantity=1, **kwargs
            ):
        self._cache = {}
        self._async_threads = []
        self.uuid = uuid.uuid4()
        self.quantity = quantity

        self.base_path = base_path or os.path.dirname(os.path.dirname(__file__))
        self.project_path = project_path
        self.name = name
        self.logger = logging.getLogger(name)

        # --- Mode propagation logic: Set global flags via classmethod ---
        explicit_modes = {}
        for flag in ('debug', 'silent', 'verbose', 'wizard', 'timed'):
            val = locals()[flag]
            if val is not None:
                explicit_modes[flag] = val
        if explicit_modes:
            type(self).update_modes(**explicit_modes)

        # Set instance mode flags to match class-level (which may have just changed)
        for flag in ('debug', 'silent', 'verbose', 'wizard'):
            setattr(self, f"{flag}_enabled", getattr(type(self), flag))
        self.timed_enabled = timed if timed is not None else getattr(type(self), 'timed', False)

        # Instance-level log helpers: always use self.<flag>() to log
        self.debug = (lambda msg, *a, **k: self.logger.debug(msg, *a, stacklevel=2, **k)) if self.debug_enabled else Null
        self.silent = (lambda msg, *a, **k: self.logger.info(msg, *a, stacklevel=2, **k)) if self.silent_enabled else Null
        self.verbose = (lambda msg, *a, **k: self.logger.info(msg, *a, stacklevel=2, **k)) if self.verbose_enabled else Null
        self.wizard = (lambda msg, *a, **k: self.logger.debug(msg, *a, stacklevel=2, **k)) if self.wizard_enabled else Null

        client_name = client or get_base_client()
        server_name = server or get_base_server()

        if not hasattr(Gateway._thread_local, "context"):
            Gateway._thread_local.context = {}
        if not hasattr(Gateway._thread_local, "results"):
            Gateway._thread_local.results = Results()

        self.context = Gateway._thread_local.context
        self.results = Gateway._thread_local.results

        # self.defaults is class-level, already initialized above

        super().__init__([
            ('results', self.results),
            ('context', self.context),
            ('env', os.environ),
        ])

        env_root = os.path.join(self.base_path, "envs")
        load_env("client", client_name, env_root)
        load_env("server", server_name, env_root)

        # Load builtins ONCE, at class level
        if Gateway._builtins is None:
            builtins_module = importlib.import_module("gway.builtins")
            Gateway._builtins = {}
            for name, obj in inspect.getmembers(builtins_module):
                if not inspect.isfunction(obj) or name.startswith("_"):
                    continue
                mod = inspect.getmodule(obj)
                if mod and mod.__name__.startswith("gway.builtins"):
                    Gateway._builtins[name] = obj

    @classmethod
    def update_modes(cls, *, debug=None, silent=None, verbose=None, wizard=None, timed=None):
        """Set global mode flags at the class level and on the global 'gw' instance, if present."""
        updated = {}
        for flag, value in [('debug', debug), ('silent', silent), ('verbose', verbose), ('wizard', wizard), ('timed', timed)]:
            if value is not None:
                setattr(cls, flag, value)
                updated[flag] = value
        # Update global gw instance if it exists and is not the current instance
        try:
            import sys
            mod = sys.modules[cls.__module__]
            if hasattr(mod, "gw"):
                g = getattr(mod, "gw")
                if isinstance(g, Gateway):
                    for flag, value in updated.items():
                        setattr(g, f"{flag}_enabled", value)
                        if flag in ('debug', 'silent', 'verbose', 'wizard'):
                            setattr(g, flag, (lambda msg, *a, **k: g.logger.debug(msg, *a, stacklevel=2, **k)) if value else Null)
        except Exception:
            pass

    @classmethod
    def set_defaults(cls, **kwargs):
        """Set (or update) default values for all Gateways."""
        cls.defaults.update(kwargs)
        logging.getLogger("gw").debug(f"Gateway.defaults updated: {cls.defaults}")

    @classmethod
    def clear_defaults(cls):
        """Remove all class-level defaults."""
        cls.defaults.clear()
        logging.getLogger("gw").debug(f"Gateway.defaults cleared")

    @classmethod
    def get_default(cls, key, default=None):
        """Fetch a default by key."""
        return cls.defaults.get(key, default)

    def projects(self):
        def discover_projects(base: Path):
            result = []
            if not base.is_dir():
                return result
            for entry in base.iterdir():
                if entry.is_file() and entry.suffix == ".py" and not entry.name.startswith("__"):
                    result.append(entry.stem)
                elif entry.is_dir() and not entry.name.startswith("__"):
                    result.append(entry.name)
            return result

        try:
            projects_path = Path(self._projects_path())
        except FileNotFoundError as e:
            self.warning(f"Could not find 'projects' directory: {e}")
            return []

        result = set(discover_projects(projects_path))
        sorted_result = sorted(result)
        self.verbose(f"Discovered projects: {sorted_result}", func="projects")
        return sorted_result

    def builtins(self):
        return sorted(Gateway._builtins)

    def success(self, message):
        print(message)
        self.info(message)

    def wrap_callable(self, func_name, func_obj, *, is_builtin=False):
        @functools.wraps(func_obj)
        def wrap(*args, **kwargs):
            try:
                start_time = time.perf_counter() if self.timed_enabled else None
                kwarg_txt = ', '.join(f"{k}='{v}'" for k, v in kwargs.items())
                arg_txt = ', '.join(f"'{x}'" for x in args)
                if kwarg_txt and arg_txt:
                    arg_txt = f"{arg_txt}, "
                if not (is_builtin and not self.verbose):
                    self.verbose(f"-> {func_name}({arg_txt}{kwarg_txt})")

                sig = inspect.signature(func_obj)
                bound_args = sig.bind_partial(*args, **kwargs)
                bound_args.apply_defaults()
                subject = self.subject(func_name)

                call_args = []
                call_kwargs = {}

                # --- NEW: defaults injection ---
                # 1. Start with the provided args/kwargs
                # 2. For any missing kwarg (not given by caller or bound by positional), inject from
                #    context/results/env as before, then finally from Gateway.defaults

                for name, param in sig.parameters.items():
                    has_explicit = name in bound_args.arguments and (
                        param.default is inspect.Parameter.empty or
                        bound_args.arguments[name] is not param.default
                    )

                    can_auto_inject = (subject is not None) and (name == subject) and not is_builtin

                    if has_explicit:
                        value = bound_args.arguments[name]
                    elif can_auto_inject:
                        value = self.find_value(name)
                        if value is None:
                            default_val = bound_args.arguments.get(name, param.default)
                            if isinstance(default_val, (Sigil, Spool)):
                                value = default_val.resolve(self)
                            else:
                                value = default_val
                    else:
                        # Check for context/env first
                        default_val = bound_args.arguments.get(name, param.default)
                        if isinstance(default_val, (Sigil, Spool)):
                            value = default_val.resolve(self)
                        else:
                            value = default_val

                        # -- Here's the new part: If still empty, pull from class-level defaults --
                        if (value is inspect.Parameter.empty or value is None) and name in type(self).defaults:
                            value = type(self).defaults[name]
                            if self.verbose:
                                self.verbose(f"Injected default {name}={value!r} from Gateway.defaults", func="wrap_callable")

                    ann = param.annotation
                    if ann in (int, float, str, bool) and value is not None and not isinstance(value, ann):
                        try:
                            value = ann(value)
                        except Exception:
                            if ann is bool and isinstance(value, str):
                                value = value.lower() in ("1", "true", "yes", "on")
                            else:
                                raise

                    if can_auto_inject:
                        self.context[name] = value

                    if param.kind == param.POSITIONAL_ONLY:
                        call_args.append(value)
                    elif param.kind == param.POSITIONAL_OR_KEYWORD:
                        call_args.append(value)
                    elif param.kind == param.VAR_POSITIONAL:
                        call_args.extend(value if isinstance(value, (list, tuple)) else [value])
                    elif param.kind == param.KEYWORD_ONLY:
                        call_kwargs[name] = value
                    elif param.kind == param.VAR_KEYWORD:
                        call_kwargs.update(value if isinstance(value, dict) else {})

                # Async handling unchanged
                if inspect.iscoroutinefunction(func_obj):
                    thread = threading.Thread(
                        target=self.run_coroutine,
                        args=(func_name, func_obj, call_args, call_kwargs),
                        daemon=True
                    )
                    self._async_threads.append(thread)
                    thread.start()
                    if start_time is not None:
                        self.log(f"[timed] {func_name} dispatch took {time.perf_counter() - start_time:.3f}s")
                    return f"ASYNC task started for {func_name}"

                result = func_obj(*call_args, **call_kwargs)

                if inspect.iscoroutine(result):
                    thread = threading.Thread(
                        target=self.run_coroutine,
                        args=(func_name, result),
                        daemon=True
                    )
                    self._async_threads.append(thread)
                    thread.start()
                    if start_time is not None:
                        self.log(f"[timed] {func_name} dispatch took {time.perf_counter() - start_time:.3f}s")
                    return f"ASYNC coroutine started for {func_name}"

                # ---- Result storage logic ----
                if not is_builtin and subject and result is not None:
                    log_value = repr(result)
                    if len(log_value) > 100:
                        log_value = log_value[:100] + "...[truncated]"
                    sensitive_keywords = ("password", "secret", "token", "key")
                    if any(word in subject for word in sensitive_keywords):
                        log_value = "[redacted]"

                    self.verbose(f"<- result['{subject}'] == {log_value}")
                    self.results.insert(subject, result)

                    if isinstance(result, dict):
                        self.context.update(result)

                if start_time is not None:
                    self.log(f"[timed] {func_name} took {time.perf_counter() - start_time:.3f}s")

                return result

            except Exception as e:
                self.error(f"Error in '{func_name}': {e}")
                if self.debug:
                    self.exception(e)
                raise

        return wrap

    def __getattr__(self, name):
        # Pass through standard logger methods if present
        if hasattr(self.logger, name) and callable(getattr(self.logger, name)):
            return getattr(self.logger, name)

        # Use class-level _builtins; never copy per-instance
        if name in Gateway._builtins:
            func = self.wrap_callable(name, Gateway._builtins[name], is_builtin=True)
            setattr(self, name, func)
            return func

        if name in self._cache:
            return self._cache[name]

        try:
            project_obj = self.load_project(project_name=name)
            return project_obj
        except FileNotFoundError as e:
            # Avoid noisy stack traces for expected missing modules
            self.debug(f"Project not found for attribute '{name}': {e}")
            raise AttributeError(f"Unable to find GWAY attribute ({str(e)})")
        except Exception as e:
            self.exception(e)
            raise AttributeError(f"Unable to find GWAY attribute ({str(e)})")
        
    def load_project(self, project_name: str, *, root: str = "projects"):
        """
        Attempt to load a project by name from all supported project locations.
        """
        def try_path(base_dir):
            base = gw.resource(base_dir, *project_name.split("."))
            self.verbose(f"{project_name} <- Project('{base}')")

            def load_module_ns(py_path: str, dotted: str):
                mod = self._load_py_file(py_path, dotted)
                funcs = {}
                for fname, obj in inspect.getmembers(mod, inspect.isfunction):
                    if not fname.startswith("_"):
                        funcs[fname] = self.wrap_callable(f"{dotted}.{fname}", obj)
                ns = Project(dotted, funcs, self)
                self._cache[dotted] = ns
                return ns

            if os.path.isdir(base):
                return self.recurse_ns(base, project_name)

            base_path = Path(base)
            py_file = base_path if base_path.suffix == ".py" else base_path.with_suffix(".py")
            if py_file.is_file():
                return load_module_ns(str(py_file), project_name)

            return None

        # 1. Use user-specified project_path if set
        if self.project_path:
            result = try_path(self.project_path)
            if result: return result

        # 2. Try _projects_path (base_path/projects, site-packages, etc)
        try:
            proj_root = self._projects_path()
            result = try_path(proj_root)
            if result: return result
        except Exception:
            pass

        # 3. Fallback: try default root (should now rarely hit)
        result = try_path(root)
        if result: return result

        raise FileNotFoundError(
            f"Project path not found for '{project_name}'. "
            f"Tried: project_path={self.project_path}, "
            f"base_path/projects, env var, site-packages, and '{root}'."
        )

    def find_project(self, *project_names: str, root: str = "projects"):
        """Return the first successfully loaded project from ``project_names``.

        Each name is passed to :meth:`load_project`. Projects that are not
        found are ignored without logging any errors. ``None`` is returned if
        none of the names can be loaded.
        """
        for proj in project_names:
            try:
                return self.load_project(proj, root=root)
            except FileNotFoundError:
                continue
        return None

    def _projects_path(self):
        """
        Find the projects directory in source, install, or user-specified locations.
        Returns the path to the projects directory if found, else raises FileNotFoundError.

        Search order:
        1. User explicitly passed a project_path (self.project_path)
        2. Check next to base_path (source/venv/dev mode)
        3. GWAY_PROJECT_PATH env variable
        4. importlib.resources for installed package data (pip install)
        """
        # 1. User explicitly passed a project_path
        if self.project_path:
            candidate = Path(self.project_path)
            if candidate.is_dir():
                return str(candidate)
        # 2. Check next to base_path (source/venv/dev mode)
        candidate = Path(self.base_path) / "projects"
        if candidate.is_dir():
            return str(candidate)
        # 3. GWAY_PROJECT_PATH env variable
        env_path = os.environ.get('GWAY_PROJECT_PATH')
        if env_path and Path(env_path).is_dir():
            return env_path
        # 4. Try importlib.resources (Python 3.9+)
        try:
            import importlib.resources as resources
            # Try to get 'projects' as a directory under the 'gway' package
            with resources.as_file(resources.files('gway').joinpath('projects')) as res_path:
                if res_path.is_dir():
                    return str(res_path)
        except Exception:
            pass
        # Not found: raise
        raise FileNotFoundError(
            "Could not locate 'projects' directory. "
            "Tried base_path, GWAY_PROJECT_PATH, and package resources."
        )
    
    def _load_py_file(self, path: str, dotted_name: str):
        """
        Don't manually use _load_py_file, instead simply access the proyect through Gateway:
        gw.project.subproject.function(), where gw is any Gateway instance such as from gway import gw.
        """
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

    def recurse_ns(self, current_path: str, dotted_prefix: str):
        """
        Recursively loads a project namespace. If a file matching the directory name
        exists (e.g. 'web/web.py'), its functions become root-level (e.g. gw.web.func).
        Subprojects (e.g. 'web/app.py') are loaded as gw.web.app.func, possibly
        shadowing root names (warn on conflicts).
        """
        funcs = {}
        subprojects = {}
        dir_basename = os.path.basename(current_path)
        root_file = os.path.join(current_path, f"{dir_basename}.py")

        # 1. Load submodules (files and directories)
        for entry in os.listdir(current_path):
            full = os.path.join(current_path, entry)
            if entry.endswith(".py") and not entry.startswith("__"):
                subname = entry[:-3]
                if subname == dir_basename:
                    continue  # defer loading the root file until later
                dotted = f"{dotted_prefix}.{subname}"
                mod = self._load_py_file(full, dotted)
                sub_funcs = {}
                for fname, obj in inspect.getmembers(mod, inspect.isfunction):
                    if not fname.startswith("_"):
                        sub_funcs[fname] = self.wrap_callable(f"{dotted}.{fname}", obj)
                subprojects[subname] = Project(dotted, sub_funcs, self)
            elif os.path.isdir(full) and not entry.startswith("__"):
                dotted = f"{dotted_prefix}.{entry}"
                subprojects[entry] = self.recurse_ns(full, dotted)

        # 2. Load the root file (e.g., web/web.py) if present
        root_funcs = {}
        if os.path.isfile(root_file):
            mod = self._load_py_file(root_file, dotted_prefix)
            for fname, obj in inspect.getmembers(mod, inspect.isfunction):
                if not fname.startswith("_"):
                    root_funcs[fname] = self.wrap_callable(f"{dotted_prefix}.{fname}", obj)

        # 3. Merge root funcs and subprojects; warn on override
        for k, v in root_funcs.items():
            if k in subprojects:
                self.warning(
                    f"Name conflict in project '{dotted_prefix}': "
                    f"root-level '{k}' from '{root_file}' is shadowed by subproject '{k}'."
                )
            funcs[k] = v
        # Insert subprojects
        for k, v in subprojects.items():
            if k in funcs:
                self.warning(
                    f"Name conflict in project '{dotted_prefix}': "
                    f"subproject '{k}' overrides root-level function '{k}'."
                )
            funcs[k] = v

        ns = Project(dotted_prefix, funcs, self)
        self._cache[dotted_prefix] = ns
        return ns

    def log(self, *args, **kwargs):
        if not self.silent:
            if self.debug:
                self.debug(*args, **kwargs)
                return "debug"
            self.info(*args, **kwargs)
            return "info"

    def subject(self, func_name: str):
        # Returns subject if "verb_subject", else None
        words = func_name.replace("-", "_").split("_")
        if len(words) > 1:
            return "_".join(words[1:])
        return None

# This line allows using "from gway import gw" everywhere else
gw = Gateway()

# TIP: It's a good idea to keep project files between 300 and 600 lines long.
