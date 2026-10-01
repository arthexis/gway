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
    owner: str | None = None
    semantic_terms: frozenset[str] = frozenset()


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
    def _semantic_terms(values):
        if values is None:
            return frozenset()
        result = frozenset(str(value).strip().lower() for value in values)
        if "" in result:
            raise ValueError("semantic terms must be non-empty strings")
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
        semantic_terms = frozenset(
            item["term"]
            for item in connection.execute(
                """
                SELECT term FROM scope_semantic_terms
                WHERE scope_id = ?
                ORDER BY term
                """,
                (scope_id,),
            )
        )
        return Scope(
            row["name"],
            operations,
            environment,
            row["owner"],
            semantic_terms,
        )

    def get(self, name, *, readonly=False):
        """Return one scope, or None without creating state."""
        if not self.path.is_file():
            return None
        name = self._name(name)
        with self.state.connect(readonly=readonly) as connection:
            row = connection.execute(
                "SELECT id, name, owner FROM scopes WHERE name = ?",
                (name,),
            ).fetchone()
            return self._row_scope(connection, row)

    def require(self, name, *, readonly=False):
        """Return one scope or fail explicitly when it does not exist."""
        scope = self.get(name, readonly=readonly)
        if scope is None:
            raise LookupError(f"Unknown security scope: {name}")
        return scope

    def all(self, *, readonly=False):
        """Return all scopes in stable name order."""
        if not self.path.is_file():
            return []
        with self.state.connect(readonly=readonly) as connection:
            rows = connection.execute(
                "SELECT id, name, owner FROM scopes ORDER BY name"
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

    def replace_owned(
        self,
        name,
        *,
        owner,
        operations=(),
        environment=(),
        semantic_terms=(),
        allow_claim_unowned=False,
    ):
        """Create or replace a scope only when its durable owner matches."""
        name = self._name(name)
        owner = str(owner).strip()
        if not owner:
            raise ValueError("scope owner must be a non-empty string")
        operations = self._grants(operations, label="operation")
        environment = self._grants(environment, label="environment")
        semantic_terms = self._semantic_terms(semantic_terms)

        with self.state.connect() as connection:
            row = connection.execute(
                "SELECT id, owner FROM scopes WHERE name = ?",
                (name,),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO scopes (name, owner) VALUES (?, ?)",
                    (name, owner),
                )
                row = connection.execute(
                    "SELECT id, owner FROM scopes WHERE name = ?",
                    (name,),
                ).fetchone()
            elif row["owner"] is None:
                if not allow_claim_unowned:
                    raise ValueError(
                        f"Security scope {name} is user-managed and cannot be claimed by {owner}"
                    )
                connection.execute(
                    "UPDATE scopes SET owner = ? WHERE id = ?",
                    (owner, row["id"]),
                )
            elif row["owner"] != owner:
                raise ValueError(
                    f"Security scope {name} is owned by {row['owner']}, not {owner}"
                )

            scope_id = row["id"]
            connection.execute(
                "DELETE FROM scope_operations WHERE scope_id = ?", (scope_id,)
            )
            connection.execute(
                "DELETE FROM scope_environment WHERE scope_id = ?", (scope_id,)
            )
            connection.execute(
                "DELETE FROM scope_semantic_terms WHERE scope_id = ?", (scope_id,)
            )
            connection.executemany(
                "INSERT INTO scope_operations (scope_id, operation) VALUES (?, ?)",
                ((scope_id, operation) for operation in sorted(operations)),
            )
            connection.executemany(
                "INSERT INTO scope_environment (scope_id, variable_name) VALUES (?, ?)",
                ((scope_id, variable) for variable in sorted(environment)),
            )
            connection.executemany(
                "INSERT INTO scope_semantic_terms (scope_id, term) VALUES (?, ?)",
                ((scope_id, term) for term in sorted(semantic_terms)),
            )
        return self.require(name)

    def remove_owned_missing(self, *, owner_prefix, active_names):
        """Remove owned scopes under a namespace that are no longer published."""
        owner_prefix = str(owner_prefix)
        active_names = frozenset(self._name(name) for name in active_names)
        removed = []
        if not self.path.is_file():
            return removed
        with self.state.connect() as connection:
            rows = connection.execute(
                "SELECT name FROM scopes WHERE owner LIKE ?",
                (owner_prefix + "%",),
            ).fetchall()
            for row in rows:
                name = row["name"]
                if name in active_names:
                    continue
                connection.execute("DELETE FROM scopes WHERE name = ?", (name,))
                removed.append(name)
        return removed

    def replace(self, name, *, operations=(), environment=(), semantic_terms=()):
        """Atomically create or replace one complete scope definition."""
        name = self._name(name)
        operations = self._grants(operations, label="operation")
        environment = self._grants(environment, label="environment")
        semantic_terms = self._semantic_terms(semantic_terms)

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
            connection.execute(
                "DELETE FROM scope_semantic_terms WHERE scope_id = ?", (scope_id,)
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
            connection.executemany(
                """
                INSERT INTO scope_semantic_terms (scope_id, term)
                VALUES (?, ?)
                """,
                ((scope_id, term) for term in sorted(semantic_terms)),
            )
        return self.require(name)

    def update_grants(
        self,
        name,
        *,
        add_operations=(),
        remove_operations=(),
        add_environment=(),
        remove_environment=(),
    ):
        """Atomically add and remove grants from one existing scope."""
        name = self._name(name)
        add_operations = self._grants(add_operations, label="operation")
        remove_operations = self._grants(remove_operations, label="operation")
        add_environment = self._grants(add_environment, label="environment")
        remove_environment = self._grants(remove_environment, label="environment")

        with self.state.connect() as connection:
            row = connection.execute(
                "SELECT id FROM scopes WHERE name = ?", (name,)
            ).fetchone()
            if row is None:
                raise LookupError(f"Unknown security scope: {name}")
            scope_id = row["id"]

            connection.executemany(
                "INSERT OR IGNORE INTO scope_operations (scope_id, operation) VALUES (?, ?)",
                ((scope_id, operation) for operation in sorted(add_operations)),
            )
            connection.executemany(
                "DELETE FROM scope_operations WHERE scope_id = ? AND operation = ?",
                ((scope_id, operation) for operation in sorted(remove_operations)),
            )
            connection.executemany(
                "INSERT OR IGNORE INTO scope_environment (scope_id, variable_name) VALUES (?, ?)",
                ((scope_id, variable) for variable in sorted(add_environment)),
            )
            connection.executemany(
                "DELETE FROM scope_environment WHERE scope_id = ? AND variable_name = ?",
                ((scope_id, variable) for variable in sorted(remove_environment)),
            )

        return self.require(name)

    def add_many(self, definitions):
        """Atomically add grants from multiple named scope definitions."""
        normalized = {}
        for name, definition in dict(definitions).items():
            name = self._name(name)
            definition = dict(definition)
            unknown = set(definition) - {"operations", "environment", "semantic_terms"}
            if unknown:
                raise ValueError(
                    f"Unknown scope fields for {name}: {', '.join(sorted(unknown))}"
                )
            normalized[name] = (
                self._grants(definition.get("operations", ()), label="operation"),
                self._grants(definition.get("environment", ()), label="environment"),
                self._semantic_terms(definition.get("semantic_terms", ())),
            )

        with self.state.connect() as connection:
            for name in sorted(normalized):
                operations, environment, semantic_terms = normalized[name]
                connection.execute(
                    "INSERT INTO scopes (name) VALUES (?) "
                    "ON CONFLICT(name) DO NOTHING",
                    (name,),
                )
                row = connection.execute(
                    "SELECT id FROM scopes WHERE name = ?",
                    (name,),
                ).fetchone()
                scope_id = row["id"]
                connection.executemany(
                    "INSERT OR IGNORE INTO scope_operations "
                    "(scope_id, operation) VALUES (?, ?)",
                    ((scope_id, operation) for operation in sorted(operations)),
                )
                connection.executemany(
                    "INSERT OR IGNORE INTO scope_environment "
                    "(scope_id, variable_name) VALUES (?, ?)",
                    ((scope_id, variable) for variable in sorted(environment)),
                )
                connection.executemany(
                    "INSERT OR IGNORE INTO scope_semantic_terms "
                    "(scope_id, term) VALUES (?, ?)",
                    ((scope_id, term) for term in sorted(semantic_terms)),
                )

        return [self.require(name) for name in sorted(normalized)]

    def replace_many(self, definitions):
        """Atomically converge multiple named scope definitions."""
        normalized = {}
        for name, definition in dict(definitions).items():
            name = self._name(name)
            definition = dict(definition)
            unknown = set(definition) - {"operations", "environment", "semantic_terms"}
            if unknown:
                raise ValueError(
                    f"Unknown scope fields for {name}: {', '.join(sorted(unknown))}"
                )
            normalized[name] = (
                self._grants(definition.get("operations", ()), label="operation"),
                self._grants(
                    definition.get("environment", ()),
                    label="environment",
                ),
                self._semantic_terms(definition.get("semantic_terms", ())),
            )

        with self.state.connect() as connection:
            for name in sorted(normalized):
                operations, environment, semantic_terms = normalized[name]
                connection.execute(
                    "INSERT INTO scopes (name) VALUES (?) "
                    "ON CONFLICT(name) DO NOTHING",
                    (name,),
                )
                row = connection.execute(
                    "SELECT id FROM scopes WHERE name = ?",
                    (name,),
                ).fetchone()
                scope_id = row["id"]
                connection.execute(
                    "DELETE FROM scope_operations WHERE scope_id = ?",
                    (scope_id,),
                )
                connection.execute(
                    "DELETE FROM scope_environment WHERE scope_id = ?",
                    (scope_id,),
                )
                connection.execute(
                    "DELETE FROM scope_semantic_terms WHERE scope_id = ?",
                    (scope_id,),
                )
                connection.executemany(
                    """
                    INSERT INTO scope_operations (scope_id, operation)
                    VALUES (?, ?)
                    """,
                    (
                        (scope_id, operation)
                        for operation in sorted(operations)
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO scope_environment (scope_id, variable_name)
                    VALUES (?, ?)
                    """,
                    (
                        (scope_id, variable_name)
                        for variable_name in sorted(environment)
                    ),
                )
                connection.executemany(
                    """
                    INSERT INTO scope_semantic_terms (scope_id, term)
                    VALUES (?, ?)
                    """,
                    ((scope_id, term) for term in sorted(semantic_terms)),
                )
        return [self.require(name) for name in sorted(normalized)]

    def rename(self, name, new_name):
        """Rename one scope while preserving grants and all bindings."""
        name = self._name(name)
        new_name = self._name(new_name)
        with self.state.connect() as connection:
            if connection.execute(
                "SELECT 1 FROM scopes WHERE name = ?",
                (new_name,),
            ).fetchone():
                raise ValueError(f"Security scope already exists: {new_name}")
            cursor = connection.execute(
                "UPDATE scopes SET name = ? WHERE name = ?",
                (new_name, name),
            )
            if not cursor.rowcount:
                raise LookupError(f"Unknown security scope: {name}")
        return self.require(new_name)

    def remove(self, name):
        """Delete one scope and its grants."""
        if not self.path.is_file():
            return False
        name = self._name(name)
        with self.state.connect() as connection:
            cursor = connection.execute("DELETE FROM scopes WHERE name = ?", (name,))
        return bool(cursor.rowcount)

    def resolve(self, names, *, readonly=False):
        """Union named scopes into one effective authority."""
        operations = builtins.set()
        environment = builtins.set()
        for name in names:
            scope = self.require(name, readonly=readonly)
            operations.update(scope.operations)
            environment.update(scope.environment)
        return EffectiveScope(frozenset(operations), frozenset(environment))
