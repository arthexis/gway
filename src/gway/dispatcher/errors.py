class DispatchError(ValueError):
    pass


class InvocationArgumentError(DispatchError):
    """Raised when literal programmatic arguments cannot be bound or converted."""

    transport_safe_argument_error = True


class CommandNotFound(DispatchError):
    pass
