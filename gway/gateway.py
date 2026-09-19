# file: gway/gateway.py

import inspect
import os
import threading

from .runner import invoke
from . import log as gway_log
from .normalization import complete_arguments
from .operations import registry_views
from .publication import publish
from .sigil import Resolver
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
        interactive=False,
        timed=False,
        **values,
    ):
        self.name = name
        self.logger = gway_log._child(name)
        self.ops, self.subs = registry_views()
        self._ingested = {}
        self.debug_enabled = bool(debug)
        self._verbose = False
        self._silent = False
        self.verbose = verbose
        self.silent = silent
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
            self.context.update({key: value for key, value in values.items() if value is not None})

        super().__init__([
            ("results", self.results),
            ("context", self.context),
            ("env", os.environ),
        ])

        from . import builtin
        from .ingestion.python import ingest_module

        ingest_module(self, builtin, path=("gway",))

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
    def verbose(self):
        """Whether this runtime emits informational logging."""
        return self._verbose

    @verbose.setter
    def verbose(self, value):
        self._verbose = bool(value)
        self._apply_logger_level()

    @property
    def silent(self):
        """Whether this runtime suppresses all logging output."""
        return self._silent

    @silent.setter
    def silent(self, value):
        self._silent = bool(value)
        self._apply_logger_level()

    def _apply_logger_level(self):
        logger = self.__dict__.get("logger")
        if logger is not None:
            logger.setLevel(
                gway_log._level(
                    verbose=self.__dict__.get("_verbose", False),
                    silent=self.__dict__.get("_silent", False),
                )
            )

    @classmethod
    def update_modes(
        cls,
        *,
        debug=None,
        verbose=None,
        silent=None,
        interactive=None,
        timed=None,
    ):
        """Update execution policy on the process-wide gw instance."""
        instance = globals().get("gw")
        if not isinstance(instance, cls):
            return
        for name, value in {
            "debug_enabled": debug,
            "interactive_enabled": interactive,
            "timed_enabled": timed,
            "verbose": verbose,
            "silent": silent,
        }.items():
            if value is not None:
                setattr(instance, name, bool(value))

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
        self.ops.register(func_name, wrapped, op=op, sub=sub)
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
        """Return the semantic subject from operation_subject or a dotted name."""
        simple = func_name.rsplit(".", 1)[-1]
        words = simple.replace("-", "_").split("_")
        if len(words) > 1:
            return "_".join(words[1:])
        parts = func_name.split(".")
        if len(parts) > 1:
            return parts[-2]
        return None


gw = Gateway()
