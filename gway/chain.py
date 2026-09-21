"""Scoped manual command chains for embedded GWAY use."""

from .dispatch import dispatch_pipeline, split_stage
from .tokens import statements, tokenize


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
        self._execution_scope = None

    def __enter__(self):
        if self._active:
            raise RuntimeError("Chain is already active")

        self._execution_scope = self.gateway.execution_scope()
        self._execution_scope.__enter__()
        try:
            self.head = self.gateway(self.command, *self.args, **self.kwargs)
        except BaseException as exception:
            self._execution_scope.__exit__(
                type(exception),
                exception,
                exception.__traceback__,
            )
            self._execution_scope = None
            raise

        self.last = self.head
        self.history.append(self.head)
        self._active = True
        return self

    def __exit__(self, exc_type, exc, traceback):
        self._active = False
        scope = self._execution_scope
        self._execution_scope = None
        if scope is None:
            return False
        return scope.__exit__(exc_type, exc, traceback)

    def __call__(self, command, *args, **kwargs):
        if not self._active:
            raise RuntimeError("Chain commands require an active with block")

        tokens = tokenize(command) if isinstance(command, str) else list(command)
        statement_list = statements(tokens)
        if len(statement_list) != 1:
            raise ValueError(
                "A chain call accepts one statement; call the chain again for the next statement"
            )

        _, remaining = split_stage(
            self.gateway,
            statement_list[0],
            pipeline=self.last,
            args=args,
            kwargs=kwargs,
        )
        if remaining:
            raise ValueError(
                "A chain call accepts one command stage; call the chain again for the next stage"
            )

        produced, result = dispatch_pipeline(
            self.gateway,
            statement_list[0],
            pipeline=self.last,
            args=args,
            kwargs=kwargs,
        )
        self.last = result
        self.history.append(result)
        return result
