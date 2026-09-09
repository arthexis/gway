class DispatchError(ValueError):
    pass


class CommandNotFound(DispatchError):
    pass
