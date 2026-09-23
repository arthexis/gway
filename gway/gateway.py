# file: gway/gateway.py

from contextlib import contextmanager
from contextvars import ContextVar
import inspect
import threading

from .runner import invoke
from .bindings import Bindings
from . import log as gway_log
from .normalization import complete_arguments
from .environment import process_environment
from .operations import registry_views, split_operation
from .publication import publish
from .sigil import Resolver
from .sigil.resolver import Environment
from .structs import Results


class Gateway(Resolver):
    """Minimal GWAY runtime: resolution, callable wrapping, and shared context."""

    _thread_local = threading.local()

    def __init__(
        self,
        *,
        context=None,
        name="gw",
        debug=False,
        verbose=False,
        silent=False,
        log_level=None,
        interactive=False,
        timed=False,
        cache=None,
        **values,
    ):
        self.name = name
        self.environment = process_environment
        self.bindings = Bindings()
        self.logger = gway_log._child(name, level=log_level)
        for level_name, level in gway_log._levels(self.logger).items():
            setattr(self, level_name, level)
        self.ops, self.subs = registry_views()

        from .launchable import Launchables

        self.launchables = Launchables()
        self._service_presets = {}
        self._ingested = {}
        self.execution = None
        self.previous_execution = None

        from .install.identity import running_gway_identity

        self.gway_identity = running_gway_identity()

        from .cache import Cache, default_root
        from .journal import JournalManager

        self.cache = cache if isinstance(cache, Cache) else Cache(cache)
        self.journal = JournalManager(default_root() / "rollback")
        self._execution_depth = 0
        self._execution_suspension = None
        self._authorization_stack_var = ContextVar(
            f"gway_authorization_stack_{id(self)}",
            default=(),
        )
        self._capability_depth_var = ContextVar(
            f"gway_capability_depth_{id(self)}",
            default=0,
        )
        self._semantic_topics_var = ContextVar(
            f"gway_semantic_topics_{id(self)}",
            default=(),
        )
        self.debug_enabled = bool(debug)
        self.verbose = bool(verbose)
        self.silent = bool(silent)
        self.interactive_enabled = bool(interactive)
        self.timed_enabled = bool(timed)

        if not hasattr(type(self)._thread_local, "context"):
            type(self)._thread_local.context = {}
        if not hasattr(type(self)._thread_local, "results"):
            type(self)._thread_local.results = Results()

        self.context = type(self)._thread_local.context
        self.results = type(self)._thread_local.results

        if context:
            self.context.update(context)
        if values:
            self.context.update(
                {key: value for key, value in values.items() if value is not None}
            )
        self.context["verbose"] = self.verbose
        self.context["silent"] = self.silent

        super().__init__(
            [
                ("results", self.results),
                ("context", self.context),
                ("bindings", self.bindings),
                (
                    "env",
                    Environment(
                        reader=self._environment_value,
                        names=self._environment_names,
                    ),
                ),
            ]
        )

        from . import builtin
        from .ingestion.python import ingest_module

        ingest_module(self, builtin, transparent=True)

        from .filesystem import Filesystem
        from .rendering import Renderer

        self._filesystem = Filesystem(self)
        self.copy = self.wrap("copy", self._filesystem.copy)
        self.move = self.wrap("move", self._filesystem.move)
        self.link = self.wrap("link", self._filesystem.link)
        self.remove = self.wrap("remove", self._filesystem.remove)

        self._renderer = Renderer(self)
        self.render = self.wrap("render", self._renderer.render)

        self.commit = self.wrap("commit", self._commit_journal)
        self.rollback = self.wrap("rollback", self._rollback_journal)
        self.clear = self.wrap("clear", self._clear_context)
        self.set_env = self.wrap("set.env", self._set_environment, op="set", sub="env")
        self.clear_env = self.wrap(
            "clear.env", self._clear_environment, op="clear", sub="env"
        )
        self.ops.register_alias("set-env", self.set_env)
        self.ops.register_alias("clear-env", self.clear_env)
        self.require = self.wrap("require", self._require)
        self.help = self.wrap("help", self._help)
        self.wrap("ingest", self.ingest)
        self.recipe = self.wrap("recipe", self._run_sampler_recipe)
        self.reload = self.wrap("reload", self._reload)

        from .config import bootstrap

        bootstrap(self)

        from .ingestion.python import ingest_python
        from .remote.service import register as register_remote_service
        from .service.controller import Controller
        from .souschef.controller import Controller as SousChefController
        from .souschef.service import register as register_souschef_service

        register_souschef_service(self)
        register_remote_service(self)

        self._service_controller = Controller(self)
        ingest_python(self, self._service_controller, path=("service",))

        from .dns import Controller as DNSController

        self._dns_controller = DNSController(self)
        ingest_python(self, self._dns_controller, path=("dns",))

        self._souschef_controller = SousChefController(self)
        ingest_python(self, self._souschef_controller, path=("sous", "chef"))

    def bind(self, semantic_key, *bindings):
        """Register ordered physical bindings for one exact semantic key."""
        return self.bindings.register(semantic_key, *bindings)

    @property
    def semantic_topics(self):
        """Return execution-local semantic topics from broadest to most-local."""
        return self._semantic_topics_var.get()

    @contextmanager
    def topics(self, *topics):
        """Temporarily extend the semantic topics used to resolve subjects."""
        normalized = tuple(str(topic).strip() for topic in topics)
        if not normalized or any(not topic for topic in normalized):
            raise ValueError("semantic topics must be non-empty")
        token = self._semantic_topics_var.set((*self.semantic_topics, *normalized))
        try:
            yield self.semantic_topics
        finally:
            self._semantic_topics_var.reset(token)

    @property
    def execution_depth(self):
        """Return the current nested GWay execution depth."""
        return self._execution_depth

    @contextmanager
    def execution_scope(self):
        """Own one nested execution scope and finalize only at the outer boundary."""
        outermost = self._execution_depth == 0
        if outermost:
            self._execution_suspension = None
        self._execution_depth += 1
        primary = None
        try:
            yield outermost
        except BaseException as exception:
            primary = exception
            raise
        finally:
            self._execution_depth -= 1
            if outermost:
                suspension = self._execution_suspension
                self._execution_suspension = None
                from .reload import ReloadTransferred

                transferred = isinstance(primary, ReloadTransferred)
                if transferred and suspension is not None:
                    self.info(
                        "execution transferred to reload checkpoint %s with "
                        "rollback session %s",
                        suspension.checkpoint_id,
                        self.journal.session_id,
                    )
                elif primary is not None:
                    self._finalize_execution(primary)
                elif suspension is None:
                    self._finalize_execution(None)
                else:
                    self.info(
                        "execution suspended for reload checkpoint %s with "
                        "rollback session %s",
                        suspension.checkpoint_id,
                        self.journal.session_id,
                    )

    def suspend_execution(self, checkpoint):
        """Transfer this outer execution boundary to one persisted reload checkpoint."""
        from .reload import ReloadCheckpoint

        if self._execution_depth <= 0:
            raise RuntimeError("execution can only be suspended from an active scope")
        if not isinstance(checkpoint, ReloadCheckpoint):
            raise TypeError("execution suspension requires a ReloadCheckpoint")

        checkpoint.validated()
        open_journals = self.journal.open_names()
        from .reload import ReloadMode

        restarting_clean = (
            checkpoint.mode is ReloadMode.RESTART
            and checkpoint.journal_session_id is None
            and not checkpoint.open_journals
            and not open_journals
        )
        if (
            not restarting_clean
            and checkpoint.journal_session_id != self.journal.session_id
        ):
            raise ValueError(
                "reload checkpoint rollback session does not match current execution"
            )

        if tuple(checkpoint.open_journals) != open_journals:
            raise ValueError(
                "reload checkpoint open journals do not match current execution"
            )

        self._execution_suspension = checkpoint
        return checkpoint

    def _finalize_execution(self, primary=None):
        """Resolve open journals at the outermost execution boundary."""
        from .journal import (
            JournalError,
            RollbackRecoveryError,
            UncommittedJournalError,
            attach_rollback_error,
        )

        open_journals = self.journal.open_names()
        if not open_journals:
            return None

        cleanup_order = tuple(reversed(open_journals))

        if primary is not None:
            rollback_errors = []
            for name in cleanup_order:
                self.info(
                    "execution failed with open rollback journal %r; "
                    "rolling back automatically",
                    name,
                )
                try:
                    self.journal.rollback(name)
                except JournalError as exception:
                    rollback_errors.append(exception)

            if len(rollback_errors) == 1:
                attach_rollback_error(primary, rollback_errors[0])
            elif rollback_errors:
                attach_rollback_error(
                    primary,
                    RollbackRecoveryError(rollback_errors),
                )
            return None

        rollback_errors = []
        for name in cleanup_order:
            self.info(
                "uncommitted rollback journal %r detected at execution boundary",
                name,
            )
            try:
                self.journal.rollback(name)
            except Exception as exception:
                rollback_errors.append(exception)

        boundary_error = UncommittedJournalError(
            open_journals,
            rollback_errors=rollback_errors,
        )
        if rollback_errors:
            raise boundary_error from rollback_errors[0]
        raise boundary_error

    def _commit_journal(self, name):
        """Commit one named rollback journal and discard its rollback material."""
        self.journal.commit(name)
        return name

    def _rollback_journal(self, name):
        """Roll back one named journal and discard it after full success."""
        self.journal.rollback(name)
        return name

    def _clear_context(self, **values):
        """Clear accumulated semantic context.

        With no named values, clear the entire context. Bare keyword flags
        remove only the corresponding context keys while preserving operation
        registration and result history.

        Args:
            values: Context-key names to remove selectively.
        """
        if values:
            for name in values:
                self.context.pop(name, None)
        else:
            self.context.clear()
        return None

    def _active_recipe_frame(self):
        frames = getattr(self, "_recipe_frames", ()) or ()
        if not frames:
            raise RuntimeError("environment mutation is only available during recipe execution")
        return frames[-1]

    def _remember_environment_value(self, frame, name):
        if name not in frame.environment_restore:
            frame.environment_restore[name] = self.environment.get(name)

    def _set_environment(self, name, value):
        """Set one environment variable for the active recipe scope.

        The override is inherited by downstream operations and child recipes,
        then restored when the current recipe frame exits.

        Args:
            name: Environment variable name.
            value: Environment variable value.
        """
        frame = self._active_recipe_frame()
        name = str(name).strip()
        if not name or "=" in name or "\x00" in name:
            raise ValueError("environment variable name must be non-empty and contain no '='")
        value = str(value)
        if "\x00" in value:
            raise ValueError("environment variable value cannot contain NUL")
        self._remember_environment_value(frame, name)
        self.environment.set(name, value)
        return value

    def _clear_environment(self, name):
        """Clear one environment variable for the active recipe scope.

        The prior value, if any, is restored when the current recipe exits.

        Args:
            name: Environment variable name.
        """
        frame = self._active_recipe_frame()
        name = str(name).strip()
        if not name or "=" in name or "\x00" in name:
            raise ValueError("environment variable name must be non-empty and contain no '='")
        self._remember_environment_value(frame, name)
        self.environment.remove(name)
        return None

    def _require(self, *packages: str, python: bool = True):
        """Declare dependencies required by the currently executing recipe.

        Python requirements are the default today. The explicit --python flag
        is retained as a backend selector so other requirement types can be
        introduced later without changing the basic command shape.

        Args:
            packages: One or more package requirement specifiers.
            python: Select Python package requirements. Defaults to true.
        """
        frames = getattr(self, "_recipe_frames", ()) or ()
        if not frames:
            raise RuntimeError("require is only available during recipe execution")
        if not packages:
            raise TypeError("require needs at least one package")
        if python is not True:
            raise ValueError("require currently supports only Python requirements")

        normalized = []
        for package in packages:
            if not isinstance(package, str) or not package.strip():
                raise ValueError("require package names must be non-empty strings")
            normalized.append(package.strip())

        frame = frames[-1]
        preflight = frame.preflight_requirements.get("python", [])
        if preflight:
            undeclared = [package for package in normalized if package not in preflight]
            if undeclared:
                raise RuntimeError(
                    "require preflight mismatch for " + ", ".join(undeclared)
                )
        else:
            if frame.uv is None:
                from .recipe.uv import ensure_uv

                frame.uv = ensure_uv(
                    system=getattr(frame.environment, "scope", "user") == "system"
                )
            from .recipe.environment import sync_python_environment

            sync_python_environment(frame.environment, frame.uv, normalized)

        requirements = frame.requirements.setdefault("python", [])
        for package in normalized:
            if package not in requirements:
                requirements.append(package)

        if frame.companion_worker is not None and not frame.companion_registered:
            from .recipe.companion import register_worker_operations

            register_worker_operations(self, frame.companion_worker)
            frame.companion_registered = True
        return tuple(requirements)

    def _run_sampler_recipe(self, recipe_name, **context):
        """Run one maintained sampler recipe."""
        from .sampler import run

        return run(self, recipe_name, **context)

    def _reload(
        self,
        timeout: float = 30.0,
        when: str | None = None,
        fresh: bool = False,
        restart: bool = False,
    ):
        """Reload GWAY in a successor process and continue the active recipe.

        Args:
            timeout: Seconds to wait for the successor to adopt the checkpoint.
            when: Reload only when the managed GWAY runtime changed.
            fresh: Resume with fresh semantic context and result history.
            restart: Roll back the current run and restart the top-level recipe.
        """
        from .reload import perform_reload

        return perform_reload(
            self,
            timeout=timeout,
            when=when,
            fresh=fresh,
            restart=restart,
        )

    def _help(self, *operation: str, verbose=False):
        """Return documentation for one Gway operation.

        Args:
            operation: Operation name parts, including an optional semantic subject.
            verbose: Include the full docstring and merged parameter details.
        """
        from .documentation import render
        from .dispatch import resolve_operation
        from .tokens import tokenize

        if not operation:
            raise TypeError("help requires an operation name")
        name = " ".join(operation)
        target, remaining, _ = resolve_operation(self, tokenize(name))
        if remaining:
            raise LookupError(f"Unable to resolve operation: {name}")
        return render(target, verbose=verbose)

    @property
    def last(self):
        """Return the raw result of the most recently completed operation."""
        return self.results.last

    def next(self, subject=None, default=...):
        """Advance an iterator result without publishing a new operation result."""
        target = self.last if subject is None else self.results[subject]
        if default is ...:
            return next(target)
        return next(target, default)

    def __next__(self):
        """Advance the current iterator result."""
        return self.next()

    @property
    def _authorization_stack(self):
        """Return the execution-local external authorization stack."""
        return self._authorization_stack_var.get()

    @property
    def authorization(self):
        """Return the active external authorization context, if any."""
        stack = self._authorization_stack
        return stack[-1] if stack else None

    @contextmanager
    def authorized(self, *, operations=(), environment=None, context=None):
        """Constrain one external request and isolate its semantic state."""
        from .authorization import Authorization

        authority = Authorization.create(
            operations=operations,
            environment=environment,
        )
        stack = self._authorization_stack
        outermost = not stack
        previous_context = None
        previous_results = None
        previous_history = None
        if outermost:
            previous_context = dict(self.context)
            previous_results = dict(self.results.maps[0])
            previous_history = list(self.results.history)
            self.context.clear()
            self.results.clear()
            self.context["verbose"] = self.verbose
            self.context["silent"] = self.silent
            if context:
                self.context.update(context)

        token = self._authorization_stack_var.set((*stack, authority))
        try:
            yield authority
        finally:
            self._authorization_stack_var.reset(token)
            if outermost:
                self.context.clear()
                self.context.update(previous_context)
                self.results.clear()
                self.results.maps[0].update(previous_results)
                self.results.history.extend(previous_history)

    @property
    def _capability_depth(self):
        """Return the execution-local trusted-capability nesting depth."""
        return self._capability_depth_var.get()

    @contextmanager
    def trusted_capability(self):
        """Temporarily execute trusted implementation details under recipe authority."""
        token = self._capability_depth_var.set(self._capability_depth + 1)
        try:
            yield
        finally:
            self._capability_depth_var.reset(token)

    @contextmanager
    def external_authority(self):
        """Re-enter the active caller authority from trusted implementation code."""
        from .authorization import AuthorizationError

        if self.authorization is None:
            raise AuthorizationError(
                "External Gateway execution requires an authorization context"
            )
        token = self._capability_depth_var.set(0)
        try:
            yield self.authorization
        finally:
            self._capability_depth_var.reset(token)

    def authorize_operation(self, operation, args=(), kwargs=None):
        """Authorize one canonical operation immediately before invocation."""
        authority = self.authorization
        if authority is None or self._capability_depth:
            return
        authority.authorize_operation(operation)
        if operation in {"env", "set.env", "clear.env"}:
            kwargs = {} if kwargs is None else kwargs
            name = args[0] if args else kwargs.get("name")
            if name is not None:
                authority.authorize_environment(str(name))

    def authorize_recipe_path(self, path):
        """Reject direct recipe-path execution under external constrained authority."""
        if self.authorization is None or self._capability_depth:
            return
        from .authorization import AuthorizationError

        raise AuthorizationError(
            "Direct recipe paths are not authorized; invoke an authorized recipe operation"
        )

    @contextmanager
    def invocation_authority(self, operation):
        """Encapsulate internals of an already-authorized trusted recipe operation."""
        if (
            self.authorization is not None
            and not self._capability_depth
            and getattr(operation, "__gway_source_kind__", None) == "recipe"
        ):
            with self.trusted_capability():
                yield
            return
        yield

    def filter_operation_result(self, operation, result):
        """Filter sensitive operation results under constrained execution."""
        authority = self.authorization
        if authority is None or self._capability_depth:
            return result
        if operation == "envs":
            return authority.filter_environment(result)
        return result

    def _environment_value(self, name):
        """Resolve one environment value through the authorized env built-in."""
        name = str(name)
        self.authorize_operation("env", args=(name, None))
        operation = self.ops.resolve("env")
        if operation is None:
            raise KeyError(name)
        builtin = getattr(operation, "__wrapped__", operation)
        value = builtin(name, None)
        if value is None:
            raise KeyError(name)
        return value

    def _environment_names(self):
        """Return only environment names visible to the active authority."""
        authority = self.authorization
        if authority is None or self._capability_depth:
            return self.environment.names()
        allowed = authority.environment
        if allowed is None:
            return ()
        if "__all__" in allowed:
            return self.environment.names()
        return tuple(name for name in allowed if name in self.environment)

    def __call__(self, command, *args, **kwargs):
        """Execute a GWAY command through the unified dispatcher."""
        from .dispatch import dispatch

        return dispatch(self, command, *args, **kwargs)

    def chain(self, command, *args, **kwargs):
        """Create a scoped manual pipeline rooted in an initial command."""
        from .chain import Chain

        return Chain(self, command, args=args, kwargs=kwargs)

    def ingest(self, source, **kwargs):
        """Ingest a Python source, qualified name, or filesystem source."""
        from .ingestion import ingest

        return ingest(self, source, **kwargs)

    def ingest_path(self, path, **kwargs):
        """Ingest a filesystem source through path-based routing."""
        from .ingestion import ingest_path

        return ingest_path(self, path, **kwargs)

    def wrap(self, func_name, func_obj, *, op=None, sub=None, receiver=None):
        """Normalize a Python callable to GWAY context and result conventions."""
        if not callable(func_obj):
            raise TypeError(f"{func_name!r} is not callable")

        subject = self.subject(func_name) if op is None else sub

        def wrapped(*args, **kwargs):
            call = complete_arguments(
                self,
                subject,
                func_obj,
                args=args,
                kwargs=kwargs,
                receiver=receiver,
            )
            result = invoke(
                self,
                func_name,
                func_obj,
                args=call.args,
                kwargs=call.kwargs,
            )
            result = self.filter_operation_result(func_name, result)
            return publish(self, subject, result)

        wrapped.__name__ = getattr(func_obj, "__name__", func_name)
        wrapped.__doc__ = getattr(func_obj, "__doc__", None)
        wrapped.__wrapped__ = func_obj
        if receiver is not None:
            signature = inspect.signature(func_obj)
            parameters = tuple(signature.parameters.values())
            if parameters:
                wrapped.__signature__ = signature.replace(parameters=parameters[1:])
        wrapped.__gway_operation__ = op or func_name
        wrapped.__gway_subject__ = subject
        wrapped.__gway_receiver__ = receiver
        self.ops.register(func_name, wrapped, op=op, sub=sub)
        self.launchables.operation(
            func_name,
            metadata={
                "operation": op or func_name,
                "subject": subject,
            },
        )
        return wrapped

    def __setattr__(self, name, value):
        object.__setattr__(self, name, value)
        if name.startswith("_") or name in {"ops", "subs"}:
            return
        ops = self.__dict__.get("ops")
        if (
            ops is not None
            and callable(value)
            and getattr(value, "__gway_operation__", None) is not None
        ):
            ops.register_alias(name, value)

    @staticmethod
    def subject(func_name: str):
        """Return the semantic subject derived by the operation registry."""
        return split_operation(func_name)[1]


gw = Gateway()
