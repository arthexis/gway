import pytest

from gway.security.defaults import CORE_SCOPE_DEFINITIONS
from gway.security.oauth import OAuthRegistry
from gway.security.scopes import ScopeRegistry
from gway.security.tokens import TokenRegistry
from sampler.github.githubops import WRITE_OPERATIONS


def test_operator_read_bundles_core_observation_surface():
    operations = CORE_SCOPE_DEFINITIONS["operator-read"]["operations"]

    assert {
        "help",
        "log.sources",
        "log.read",
        "log.search",
        "log.tail",
        "security.whoami",
        "security.scope.current",
    } <= operations


def test_operator_write_is_the_curated_github_write_family():
    operations = CORE_SCOPE_DEFINITIONS["operator-write"]["operations"]

    assert operations == frozenset(f"github.{name}" for name in WRITE_OPERATIONS)
    assert "github.drive" in operations


def test_token_rename_preserves_bearer_scope_and_oauth_identity(tmp_path):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    oauth = OAuthRegistry(path)
    scopes.replace("operator-read", operations={"log.read"})
    issued = tokens.create("old-name", scopes={"operator-read"})
    oauth.link("chatgpt", "old-name")
    grant = oauth.create_grant(
        "chatgpt",
        "chatgpt-client",
        scopes={"operator-read"},
    )

    renamed = tokens.rename("old-name", "new-name")

    assert renamed.name == "new-name"
    assert renamed.public_id == issued.token.public_id
    assert renamed.scopes == issued.token.scopes
    assert tokens.get("old-name") is None
    authenticated = tokens.authenticate(issued.bearer)
    assert authenticated.token.name == "new-name"
    assert authenticated.token.public_id == issued.token.public_id
    assert authenticated.authority.operations == frozenset({"log.read"})
    assert oauth.get_link("chatgpt").token_name == "new-name"
    assert oauth.get_grant(grant.id).scopes == frozenset({"operator-read"})


def test_token_rename_rejects_invalid_changes_atomically(tmp_path):
    path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(path)
    tokens = TokenRegistry(path)
    scopes.create("operator-read")
    first = tokens.create("first", scopes={"operator-read"})
    tokens.create("second", scopes={"operator-read"})

    with pytest.raises(LookupError, match="Unknown security token"):
        tokens.rename("missing", "renamed")
    with pytest.raises(ValueError, match="non-empty"):
        tokens.rename("first", "")
    with pytest.raises(ValueError, match="already exists"):
        tokens.rename("first", "second")

    unchanged = tokens.require("first")
    assert unchanged.public_id == first.token.public_id
    assert unchanged.scopes == frozenset({"operator-read"})
    assert tokens.authenticate(first.bearer).token.name == "first"


def test_security_token_rename_command_uses_registry_identity(gateway, tmp_path):
    gateway.security_path = tmp_path / "security.sqlite"
    scopes = ScopeRegistry(gateway.security_path)
    scopes.create("operator-read")
    bearer = gateway("security token create old-name operator-read")
    before = gateway("security token show old-name")

    renamed = gateway("security token rename old-name new-name")

    assert renamed.name == "new-name"
    assert renamed.public_id == before.public_id
    assert gateway("security token show new-name").public_id == before.public_id
    assert TokenRegistry(gateway.security_path).authenticate(bearer).token.name == "new-name"
