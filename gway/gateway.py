# file: gway/gateway.py

from contextlib import contextmanager
import inspect
import threading

from .runner import invoke
from . import log as gway_log
from .normalization import complete_arguments
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
                ("env", Environment()),
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
        self.help = self.wrap("help", self._help)
        self.wrap("ingest", self.ingest)
        self.recipe = self.wrap("recipe", self._run_bundled_recipe)
        self.reload = self.wrap("reload", self._reload)

        from .config import bootstrap

        bootstrap(self)

        from .ingestion.python import ingest_python
        from .service.controller import Controller
        from .souschef.controller import Controller as SousChefController
        from .souschef.service import register as register_souschef_service

        register_souschef_service(self)

        self._service_controller = Controller(self)
        ingest_python(self, self._service_controller, path=("service",))

        self._souschef_controller = SousChefController(self)
        ingest_python(self, self._souschef_controller, path=("sous", "chef"))

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
        if checkpoint.journal_session_id != self.journal.session_id:
            raise ValueError(
                "reload checkpoint rollback session does not match current execution"
            )

        open_journals = self.journal.open_names()
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

    def _run_bundled_recipe(self, recipe_name, **context):
        """Run one recipe bundled with the installed Gway package."""
        from .bundled import run

        return run(self, recipe_name, **context)

    def _reload(self, timeout: float = 30.0):
        """Reload GWAY in a successor process and continue the active recipe.

        Args:
            timeout: Seconds to wait for the successor to adopt the checkpoint.
        """
        from .reload import perform_reload

        return perform_reload(self, timeout=timeout)

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
