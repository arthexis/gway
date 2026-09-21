"""Execution identity policy shared by host-affecting operations."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionIdentity:
    """Requested operating-system user for one execution."""

    user: str | None = None

    def __post_init__(self):
        if self.user is None:
            return
        user = str(self.user).strip()
        if not user:
            raise ValueError("Execution user cannot be empty")
        object.__setattr__(self, "user", user)

    @property
    def privileged(self):
        """Return whether execution requests an explicit user identity."""
        return self.user is not None

    def prefix(self):
        """Return the current Unix command prefix for this identity."""
        if self.user is None:
            return ()
        if self.user == "root":
            return ("sudo",)
        return ("sudo", "-u", self.user)

    def command(self, *argv):
        """Apply this identity to one external command argv."""
        return (*self.prefix(), *(str(argument) for argument in argv))

    def as_dict(self):
        """Serialize this identity for persistent transaction metadata."""
        return {"user": self.user}

    @classmethod
    def from_dict(cls, value):
        """Restore a normalized execution identity from persisted metadata."""
        value = dict(value or {})
        unknown = set(value) - {"user"}
        if unknown:
            names = ", ".join(sorted(unknown))
            raise ValueError(f"Unknown execution identity fields: {names}")
        return cls(value.get("user"))


def execution_identity(*, as_user=None, sudo=False, options=None):
    """Normalize --as/--sudo semantics into one execution identity."""
    options = {} if options is None else dict(options)
    cli_user = options.pop("as", None)
    if as_user is not None and cli_user is not None and str(as_user) != str(cli_user):
        raise ValueError("Conflicting execution users supplied")
    if options:
        unknown = ", ".join(sorted(options))
        raise TypeError(f"Unknown execution identity options: {unknown}")

    user = as_user if as_user is not None else cli_user
    if sudo and user not in (None, "root"):
        raise ValueError("--sudo conflicts with --as unless --as root is used")
    return ExecutionIdentity("root" if sudo else user)
