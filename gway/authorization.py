"""Execution authorization primitives for externally constrained Gateway calls."""

from dataclasses import dataclass


class AuthorizationError(PermissionError):
    """Raised when constrained execution attempts an unauthorized action."""


@dataclass(frozen=True)
class Authorization:
    """Effective authority for one externally constrained execution."""

    operations: frozenset[str]
    environment: frozenset[str] | None = None
    kind: str | None = None
    principal: str | None = None
    client_id: str | None = None
    scopes: frozenset[str] = frozenset()

    @classmethod
    def create(
        cls,
        operations=(),
        environment=None,
        *,
        kind=None,
        principal=None,
        client_id=None,
        scopes=(),
    ):
        return cls(
            operations=frozenset(str(name) for name in operations),
            environment=(
                None
                if environment is None
                else frozenset(str(name) for name in environment)
            ),
            kind=None if kind is None else str(kind),
            principal=None if principal is None else str(principal),
            client_id=None if client_id is None else str(client_id),
            scopes=frozenset(str(name) for name in scopes),
        )

    def authorize_operation(self, name):
        if "__all__" not in self.operations and name not in self.operations:
            raise AuthorizationError(f"Operation is not authorized: {name}")

    def authorize_environment(self, name):
        allowed = self.environment
        if allowed is None:
            raise AuthorizationError("Environment access is not authorized")
        if "__all__" not in allowed and name not in allowed:
            raise AuthorizationError(f"Environment variable is not authorized: {name}")

    def filter_environment(self, values):
        allowed = self.environment
        if allowed is None:
            return {}
        if "__all__" in allowed:
            return dict(values)
        return {name: values[name] for name in allowed if name in values}
