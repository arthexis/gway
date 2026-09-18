# file: gway/gateway.py

import logging
import os
import threading

from .runner import invoke
from .normalization import complete_arguments
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
        self.logger = logging.getLogger(name)
        self.debug_enabled = bool(debug)
        self.verbose_enabled = bool(verbose)
        self.silent_enabled = bool(silent)
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

    @property
    def last(self):
        """Return the raw result of the most recently completed operation."""
        return self.results.last

    def debug(self, message, *args, **kwargs):
        if self.debug_enabled:
            return self.logger.debug(message, *args, **kwargs)

    def verbose(self, message, *args, **kwargs):
        if self.verbose_enabled:
            return self.logger.info(message, *args, **kwargs)

    def info(self, message, *args, **kwargs):
        return self.logger.info(message, *args, **kwargs)

    def warning(self, message, *args, **kwargs):
        return self.logger.warning(message, *args, **kwargs)

    warn = warning

    def error(self, message, *args, **kwargs):
        return self.logger.error(message, *args, **kwargs)

    def exception(self, exception, *args, **kwargs):
        if isinstance(exception, BaseException):
            return self.logger.exception(str(exception), *args, **kwargs)
        return self.logger.exception(exception, *args, **kwargs)

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
            "debug": debug,
            "verbose": verbose,
            "silent": silent,
            "interactive": interactive,
            "timed": timed,
        }.items():
            if value is not None:
                setattr(instance, f"{name}_enabled", bool(value))

    def __call__(self, command, *args, **kwargs):
        """Execute a GWAY command, optionally with native Python arguments."""
        from .console import _resolve_operation, process
        from .tokens import chunk, tokenize

        if isinstance(command, str):
            tokens = tokenize(command)
        else:
            tokens = list(command)

        if not tokens:
            raise ValueError("Gateway command cannot be empty")

        if args or kwargs:
            func, remaining, _ = _resolve_operation(self, tokens)
            if remaining:
                raise TypeError(
                    "Native arguments require an operation name without inline arguments"
                )
            return func(*args, **kwargs)

        commands = chunk(tokens)
        _, result = process(commands, gw_instance=self)
        return result

    def wrap(self, func_name, func_obj):
        """Normalize a Python callable to GWAY context and result conventions."""
        if not callable(func_obj):
            raise TypeError(f"{func_name!r} is not callable")

        subject = self.subject(func_name)

        def wrapped(*args, **kwargs):
            call = complete_arguments(
                self,
                subject,
                func_obj,
                args=args,
                kwargs=kwargs,
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
        return wrapped

    def __getattr__(self, name):
        logger_method = getattr(self.logger, name, None)
        if callable(logger_method):
            return logger_method
        raise AttributeError(name)

    @staticmethod
    def subject(func_name: str):
        """Return the semantic subject from verb_subject or a dotted name."""
        simple = func_name.rsplit(".", 1)[-1]
        words = simple.replace("-", "_").split("_")
        if len(words) > 1:
            return "_".join(words[1:])
        parts = func_name.split(".")
        if len(parts) > 1:
            return parts[-2]
        return None


gw = Gateway()
