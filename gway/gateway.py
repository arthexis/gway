# file: gway/gateway.py

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

        from .cache import Cache

        self.cache = cache if isinstance(cache, Cache) else Cache(cache)
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
        self.clear = self.wrap("clear", self._clear_context)
        self.help = self.wrap("help", self._help)

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
