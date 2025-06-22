# file: gway/gateway.py

import os
import re
import sys
import uuid
import inspect
import logging
import threading
import importlib
import functools

from regex import W
from pathlib import Path

from .envs import load_env, get_base_client, get_base_server
from .sigils import Resolver
from .structs import Results, Project, Null
from .runner import Runner


class Gateway(Resolver, Runner):
    _builtins = None  # Class-level: stores all discovered builtins only once
    _thread_local = threading.local()

    Null = Null  # Null is a black-hole, assign with care.

    # Global state (typically set from CLI)
    debug = False
    silent = False
    verbose = False
    wizard = False

    def __init__(self, *, 
                client=None, server=None, name="gw", base_path=None, project_path=None,
                verbose=False, silent=False, debug=None, wizard=None, quantity=1, **kwargs
    ):
        self._cache = {}
        self._async_threads = []
        self.uuid = uuid.uuid4()
        self.quantity = quantity

        self.base_path = base_path or os.path.dirname(os.path.dirname(__file__))
        self.project_path = project_path
        self.name = name
        self.logger = logging.getLogger(name)

        # Configure log level helpers
        if debug is not None:
            Gateway.debug = (lambda self, msg: self.logger.debug(msg, stacklevel=2)) if debug else Null
        if silent is not None:
            Gateway.silent = (lambda self, msg: self.logger.info(msg, stacklevel=2)) if silent else Null
        if verbose is not None:
            Gateway.verbose = (lambda self, msg: self.logger.info(msg, stacklevel=2)) if verbose else Null
        if wizard is not None:
            Gateway.verbose = (lambda self, msg: self.logger.debug(msg, stacklevel=2)) if wizard else Null

        client_name = client or get_base_client()
        server_name = server or get_base_server()

        if not hasattr(Gateway._thread_local, "context"):
            Gateway._thread_local.context = {}
        if not hasattr(Gateway._thread_local, "results"):
            Gateway._thread_local.results = Results()

        self.context = Gateway._thread_local.context
        self.results = Gateway._thread_local.results

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
            Gateway._builtins = {
                name: obj
                for name, obj in inspect.getmembers(builtins_module)
                if inspect.isfunction(obj)
                and not name.startswith("_")
                and inspect.getmodule(obj) == builtins_module
            }

    def _projects_path(self):
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
            with resources.as_file(resources.files('gway').joinpath('projects')) as res_path:
                if res_path.is_dir():
                    return str(res_path)
        except Exception:
            pass
        raise FileNotFoundError(
            "Could not locate 'projects' directory. "
            "Tried base_path, GWAY_PROJECT_PATH, and package resources."
        )

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

    def load_project(self, project_name: str, *, root: str = "projects"):
        """Attempt to load a project by name from all supported project locations."""
        def try_path(base_dir):
            base = gw.resource(base_dir, *project_name.split("."))
            self.debug(f"{project_name} <- Project('{base}')")

            def load_module_ns(py_path: str, dotted: str):
                mod = self.load_py_file(py_path, dotted)
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

        if self.project_path:  # 1. Use user-specified project_path if set
            result = try_path(self.project_path)
            if result:
                return result
            
        try:  # 2. Try _projects_path (base_path/projects, site-packages, etc)
            proj_root = self._projects_path()
            result = try_path(proj_root)
            if result:
                return result
        except Exception:
            pass

        result = try_path(root)  # 3. Fallback: try default root (should now rarely hit)
        if result:
            return result

        raise FileNotFoundError(
            f"Project path not found for '{project_name}'. "
            f"Tried: project_path={self.project_path}, "
            f"base_path/projects, env var, site-packages, and '{root}'."
        )

    def builtins(self):
        return sorted(Gateway._builtins)

    def success(self, message):
        print(message)
        self.info(message)

    def wrap_callable(self, func_name, func_obj, *, is_builtin=False):
        @functools.wraps(func_obj)
        def wrap(*args, **kwargs):
            try:
                kwarg_txt = ', '.join(f"{k}='{v}'" for k, v in kwargs.items())
                arg_txt = ', '.join(f"'{x}'" for x in args)
                if kwarg_txt and arg_txt:
                    arg_txt = f"{arg_txt}, "
                # Only log call for builtins if verbose; otherwise, always log for non-builtins
                if not (is_builtin and not self.verbose):
                    self.debug(f"> {func_name}({arg_txt}{kwarg_txt})")
                sig = inspect.signature(func_obj)
                bound_args = sig.bind_partial(*args, **kwargs)
                bound_args.apply_defaults()

                # --- Step 1: NO automatic resolution of defaults here ---
                # (context injection handled by fallback in Step 3)

                # --- Step 2: NO automatic resolution of argument values ---
                # Instead, just copy into context
                for key, value in bound_args.arguments.items():
                    self.context[key] = value

                # Step 3: Prepare final call args/kwargs (context fallback intact)
                args_to_pass = []
                kwargs_to_pass = {}
                for param in sig.parameters.values():
                    if param.kind == param.VAR_POSITIONAL:
                        args_to_pass.extend(bound_args.arguments.get(param.name, ()))
                    elif param.kind == param.VAR_KEYWORD:
                        kwargs_to_pass.update(bound_args.arguments.get(param.name, {}))
                    elif param.name in bound_args.arguments:
                        val = bound_args.arguments[param.name]
                        # If argument is still the default, try to override from context
                        if param.default == val:
                            found = self.find_value(param.name)
                            if found is not None and found != val:
                                val = found
                                self.context[param.name] = val
                        kwargs_to_pass[param.name] = val

                # Step 4: Call the function (async or sync)
                if inspect.iscoroutinefunction(func_obj):
                    thread = threading.Thread(
                        target=self.run_coroutine,
                        args=(func_name, func_obj, args_to_pass, kwargs_to_pass),
                        daemon=True
                    )
                    self._async_threads.append(thread)
                    thread.start()
                    return f"ASYNC task started for {func_name}"

                result = func_obj(*args_to_pass, **kwargs_to_pass)

                if inspect.iscoroutine(result):
                    thread = threading.Thread(
                        target=self.run_coroutine,
                        args=(func_name, result),
                        daemon=True
                    )
                    self._async_threads.append(thread)
                    thread.start()
                    return f"ASYNC coroutine started for {func_name}"

                # Step 5: Store result into results/context if not None
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

                    repr_result = repr(result)
                    if len(repr_result) > 100:
                        short_result = repr_result[:100] + "...[truncated]"
                    else:
                        short_result = repr_result

                    sensitive_keywords = ("password", "secret", "token", "key")
                    if any(word.lower() in sk.lower() for word in sensitive_keywords):
                        log_value = "<redacted>"
                    else:
                        log_value = short_result

                    # Only log result for builtins if verbose; otherwise, always log for non-builtins
                    if not (is_builtin and not self.verbose):
                        self.debug(f"< result['{sk}'] == {log_value}")
                    self.results.insert(sk, result)
                    if lk != sk:
                        self.results.insert(lk, result)
                    if isinstance(result, dict):
                        self.context.update(result)

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
        except Exception as e:
            self.exception(e)
            raise AttributeError(f"Unable to find GWAY attribute ({str(e)})")
        
    def load_project(self, project_name: str, *, root: str = "projects"):
        """
        Attempt to load a project by name from all supported project locations.
        """
        def try_path(base_dir):
            base = gw.resource(base_dir, *project_name.split("."))
            self.debug(f"{project_name} <- Project('{base}')")

            def load_module_ns(py_path: str, dotted: str):
                mod = self.load_py_file(py_path, dotted)
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

    def _projects_path(self):
        """
        Find the projects directory in source, install, or user-specified locations.
        Returns the path to the projects directory if found, else raises FileNotFoundError.
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
        # 4. Try site-packages data (pip install, wheel)
        try:
            res_path = pkg_resources.resource_filename('gway', '../projects')
            if os.path.isdir(res_path):
                return res_path
        except Exception:
            pass
        # 5. Try as data file (if installed via data_files entry)
        try:
            res_path = pkg_resources.resource_filename('gway_projects', '')
            if os.path.isdir(res_path):
                return res_path
        except Exception:
            pass
        raise FileNotFoundError(
            "Could not locate 'projects' directory. "
            "Tried base_path, GWAY_PROJECT_PATH, site-packages, and user data dirs."
        )

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
                mod = self.load_py_file(full, dotted)
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
            mod = self.load_py_file(root_file, dotted_prefix)
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


# This line allows using "from gway import gw" everywhere else
gw = Gateway()

# TIP: It's a good idea to keep project files between 300 and 600 lines long.
