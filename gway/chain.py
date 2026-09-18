"""Scoped manual command chains for embedded GWAY use."""

from .binding import bind_arguments
from .console import _resolve_operation
from .tokens import chunk, tokenize


class Chain:
    """A scoped callable pipeline rooted in a Gateway command."""

    def __init__(self, gateway, command, args=(), kwargs=None):
        self.gateway = gateway
        self.command = command
        self.args = tuple(args)
        self.kwargs = {} if kwargs is None else dict(kwargs)
        self.head = None
        self.last = None
        self.history = []
        self._active = False

    def __enter__(self):
        if self._active:
            raise RuntimeError("Chain is already active")

        self.head = self.gateway(self.command, *self.args, **self.kwargs)
        self.last = self.head
        self.history.append(self.head)
        self._active = True
        return self

    def __exit__(self, exc_type, exc, traceback):
        self._active = False
        return False

    def __call__(self, command, *args, **kwargs):
        if not self._active:
            raise RuntimeError("Chain commands require an active with block")

        tokens = tokenize(command) if isinstance(command, str) else list(command)
        commands = chunk(tokens)
        if len(commands) != 1:
            raise ValueError(
                "A chain call accepts one command stage; call the chain again for the next stage"
            )

        func, arguments, _ = _resolve_operation(self.gateway, commands[0])
        bound = bind_arguments(
            func,
            arguments,
            runtime=self.gateway,
            interactive=self.gateway.interactive_enabled,
            initial_args=(self.last, *args),
            initial_kwargs=kwargs,
        )
        result = func(*bound.args, **bound.kwargs)
        self.last = result
        self.history.append(result)
        return result
