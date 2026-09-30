import sqlite3

from gway.security.defaults import converge_scope_registry
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry


def test_semantic_terms_round_trip_as_canonical_unordered_metadata(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")

    scope = registry.replace(
        "odoo-cards-read",
        operations={"odoo.cards.list"},
        semantic_terms=["Read", "cards", "odoo", "cards"],
    )

    assert scope.semantic_terms == frozenset({"odoo", "cards", "read"})
    assert registry.require("odoo-cards-read").semantic_terms == scope.semantic_terms


def test_scope_name_does_not_infer_semantic_terms(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")

    scope = registry.replace("odoo-cards-read", operations={"odoo.cards.list"})

    assert scope.semantic_terms == frozenset()


def test_existing_v7_scope_database_migrates_without_reinterpreting_scopes(tmp_path):
    path = tmp_path / "security.sqlite"
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE scopes (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                owner TEXT
            );
            CREATE TABLE scope_operations (
                scope_id INTEGER NOT NULL,
                operation TEXT NOT NULL,
                UNIQUE(scope_id, operation),
                FOREIGN KEY(scope_id) REFERENCES scopes(id) ON DELETE CASCADE
            );
            CREATE TABLE scope_environment (
                scope_id INTEGER NOT NULL,
                variable_name TEXT NOT NULL,
                UNIQUE(scope_id, variable_name),
                FOREIGN KEY(scope_id) REFERENCES scopes(id) ON DELETE CASCADE
            );
            INSERT INTO scopes (id, name) VALUES (1, 'logs-read');
            INSERT INTO scope_operations (scope_id, operation) VALUES (1, 'log.read');
            PRAGMA user_version = 7;
            """
        )

    scope = ScopeRegistry(path).require("logs-read")

    assert scope.operations == frozenset({"log.read"})
    assert scope.semantic_terms == frozenset()
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 8
        assert connection.execute(
            "SELECT COUNT(*) FROM scope_semantic_terms"
        ).fetchone()[0] == 0


def test_semantic_metadata_does_not_change_exact_token_authority(tmp_path):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    scopes.replace(
        "odoo-cards-read",
        operations={"odoo.cards.list"},
        semantic_terms={"odoo", "cards", "read"},
    )
    scopes.replace(
        "arthexis-cards-read",
        operations={"arthexis.cards.list"},
        semantic_terms={"arthexis", "cards", "read"},
    )

    issued = tokens.create("odoo-only", scopes={"odoo-cards-read"})
    identity = tokens.authenticate(issued.bearer)

    assert identity.authority.operations == frozenset({"odoo.cards.list"})
    assert "arthexis.cards.list" not in identity.authority.operations


def test_product_publication_persists_optional_semantic_terms(tmp_path):
    registry = ScopeRegistry(tmp_path / "security.sqlite")

    converge_scope_registry(
        registry,
        {
            "odoo-cards-read": {
                "source": "odoo",
                "operations": {"odoo.cards.list"},
                "semantic_terms": {"odoo", "cards", "read"},
            }
        },
    )

    published = registry.require("odoo-cards-read")
    assert published.owner == "project:odoo"
    assert published.semantic_terms == frozenset({"odoo", "cards", "read"})
    assert registry.require("logs-read").semantic_terms == frozenset()


def test_semantic_terms_toml_round_trip(gateway, tmp_path):
    source = tmp_path / "scopes.toml"
    source.write_text(
        """
[scopes.odoo-cards-read]
operations = ["odoo.cards.list"]
environment = []
semantic_terms = ["read", "cards", "odoo"]
""".lstrip(),
        encoding="utf-8",
    )
    gateway.security_path = tmp_path / "security.sqlite"

    gateway(f"security scope apply {source}")
    scope = ScopeRegistry(gateway.security_path).require("odoo-cards-read")
    assert scope.semantic_terms == frozenset({"odoo", "cards", "read"})

    exported = tmp_path / "exported.toml"
    gateway(f"security scope export --to {exported}")
    rendered = exported.read_text(encoding="utf-8")
    assert 'semantic_terms = ["cards", "odoo", "read"]' in rendered

    gateway.security_path = tmp_path / "replacement.sqlite"
    gateway(f"security scope apply {exported}")
    replacement = ScopeRegistry(gateway.security_path).require("odoo-cards-read")
    assert replacement.semantic_terms == scope.semantic_terms
