"""Named reusable authorization scopes."""

import builtins
from dataclasses import dataclass
from ..cache import default_root
from .state import SecurityState


@dataclass(frozen=True)
class Scope:
    """One durable named grant set."""

    name: str
    operations: frozenset[str] = frozenset()
    environment: frozenset[str] = frozenset()


@dataclass(frozen=True)
class EffectiveScope:
    """Union of one or more named scopes."""

    operations: frozenset[str] = frozenset()
    environment: frozenset[str] = frozenset()


class ScopeRegistry:
    """CRUD and composition for named security scopes."""

    def __init__(self, path=None):
        path = default_root() / "security" / "state.sqlite" if path is None else path
        self.state = SecurityState(path)

    @property
    def path(self):
        return self.state.path

    @staticmethod
    def _name(value):
        value = str(value).strip()
        if not value:
            raise ValueError("scope name must be a non-empty string")
        return value

    @staticmethod
    def _grants(values, *, label):
        if values is None:
            return frozenset()
        result = frozenset(str(value).strip() for value in values)
        if "" in result:
            raise ValueError(f"{label} grants must be non-empty strings")
        return result

    @staticmethod
    def _row_scope(connection, row):
        if row is None:
            return None
        scope_id = row["id"]
        operations = frozenset(
            item["operation"]
            for item in connection.execute(
                """
                SELECT operation FROM scope_operations
                WHERE scope_id = ?
                ORDER BY operation
                """,
                (scope_id,),
            )
        )
        environment = frozenset(
            item["variable_name"]
            for item in connection.execute(
                """
                SELECT variable_name FROM scope_environment
                WHERE scope_id = ?
                ORDER BY variable_name
                """,
                (scope_id,),
            )
        )
        return Scope(row["name"], operations, environment)

    def get(self, name):
        """Return one scope, or None without creating state."""
        if not self.path.is_file():
            return None
        name = self._name(name)
        with self.state.connect() as connection:
            row = connection.execute(
                "SELECT id, name FROM scopes WHERE name = ?",
                (name,),
            ).fetchone()
            return self._row_scope(connection, row)

    def require(self, name):
        """Return one scope or fail explicitly when it does not exist."""
        scope = self.get(name)
        if scope is None:
            raise LookupError(f"Unknown security scope: {name}")
        return scope

    def all(self):
        """Return all scopes in stable name order."""
        if not self.path.is_file():
            return []
        with self.state.connect() as connection:
            rows = connection.execute(
                "SELECT id, name FROM scopes ORDER BY name"
            ).fetchall()
            return [self._row_scope(connection, row) for row in rows]

    def create(self, name):
        """Create an empty scope and fail when the name already exists."""
        name = self._name(name)
        with self.state.connect() as connection:
            try:
                connection.execute("INSERT INTO scopes (name) VALUES (?)", (name,))
            except Exception:
                if connection.execute(
                    "SELECT 1 FROM scopes WHERE name = ?", (name,)
                ).fetchone():
                    raise ValueError(f"Security scope already exists: {name}") from None
                raise
        return self.require(name)

    def replace(self, name, *, operations=(), environment=()):
        """Atomically create or replace one complete scope definition."""
        name = self._name(name)
        operations = self._grants(operations, label="operation")
        environment = self._grants(environment, label="environment")

        with self.state.connect() as connection:
            connection.execute(
                "INSERT INTO scopes (name) VALUES (?) ON CONFLICT(name) DO NOTHING",
                (name,),
            )
            row = connection.execute(
                "SELECT id FROM scopes WHERE name = ?", (name,)
            ).fetchone()
            scope_id = row["id"]
            connection.execute(
                "DELETE FROM scope_operations WHERE scope_id = ?", (scope_id,)
            )
            connection.execute(
                "DELETE FROM scope_environment WHERE scope_id = ?", (scope_id,)
            )
            connection.executemany(
                """
                INSERT INTO scope_operations (scope_id, operation)
                VALUES (?, ?)
                """,
                ((scope_id, operation) for operation in sorted(operations)),
            )
            connection.executemany(
                """
                INSERT INTO scope_environment (scope_id, variable_name)
                VALUES (?, ?)
                """,
                ((scope_id, name) for name in sorted(environment)),
            )
        return self.require(name)

    def remove(self, name):
        """Delete one scope and its grants."""
        if not self.path.is_file():
            return False
        name = self._name(name)
        with self.state.connect() as connection:
            cursor = connection.execute("DELETE FROM scopes WHERE name = ?", (name,))
        return bool(cursor.rowcount)

    def resolve(self, names):
        """Union named scopes into one effective authority."""
        operations = builtins.set()
        environment = builtins.set()
        for name in names:
            scope = self.require(name)
            operations.update(scope.operations)
            environment.update(scope.environment)
        return EffectiveScope(frozenset(operations), frozenset(environment))

