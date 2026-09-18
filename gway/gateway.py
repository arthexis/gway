# file: gway/gateway.py

import inspect
import logging
import os
import threading
import time

from .binding import Literal
from .runner import Runner
from .sigils import Resolver, Sigil, Spool
from .structs import Results


class Gateway(Resolver, Runner):
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
        self._async_threads = []

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

    def wrap_callable(self, func_name, func_obj):
        """Adapt a Python callable to GWAY context and result conventions."""
        if not callable(func_obj):
            raise TypeError(f"{func_name!r} is not callable")

        def wrapped(*args, **kwargs):
            start = time.perf_counter() if self.timed_enabled else None
            signature = inspect.signature(func_obj)
            bound = signature.bind_partial(*args, **kwargs)
            subject = self.subject(func_name)

            call_args = []
            call_kwargs = {}
            for name, parameter in signature.parameters.items():
                if name in bound.arguments:
                    value = bound.arguments[name]
                elif subject and name == subject:
                    value = self.find_value(name)
                    if value is None:
                        value = parameter.default
                else:
                    value = parameter.default

                if isinstance(value, (Sigil, Spool)):
                    value = value.resolve(self)

                if value is inspect.Parameter.empty:
                    raise TypeError(f"missing required argument: {name}")

                if isinstance(value, Literal):
                    value = str(value)

                if parameter.kind is inspect.Parameter.POSITIONAL_ONLY:
                    call_args.append(value)
                elif parameter.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD:
                    call_args.append(value)
                elif parameter.kind is inspect.Parameter.VAR_POSITIONAL:
                    call_args.extend(value)
                elif parameter.kind is inspect.Parameter.KEYWORD_ONLY:
                    call_kwargs[name] = value
                elif parameter.kind is inspect.Parameter.VAR_KEYWORD:
                    call_kwargs.update(value)

            result = func_obj(*call_args, **call_kwargs)
            if inspect.isawaitable(result):
                return self.run_coroutine(func_name, result)

            if subject and result is not None:
                self.results.insert(subject, result)
                if isinstance(result, dict):
                    self.context.update(result)

            if start is not None:
                self.logger.info(
                    "[timed] %s took %.3fs",
                    func_name,
                    time.perf_counter() - start,
                )
            return result

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
