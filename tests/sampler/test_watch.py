import pytest

from gway import Gateway
from gway.authorization import AuthorizationError
from gway.security.scopes import ScopeRegistry


EXPECTED_SECTIONS = {
    "node",
    "health",
    "services",
    "deploy",
    "release",
    "queue",
    "wire",
    "errors",
    "changed_at",
    "cursor",
}


class FakeGitHub:
    def pulls(self, repository, state="open"):
        return []

    def runs(self, repository):
        return [
            {
                "id": 7,
                "name": "Watchtower candidate",
                "path": ".github/workflows/watchtower-candidate.yml",
                "event": "push",
                "status": "completed",
                "conclusion": "success",
                "head_sha": "abc",
                "head_branch": "main",
                "created_at": "2026-09-28T00:00:00Z",
                "updated_at": "2026-09-28T00:01:00Z",
                "html_url": "https://example.invalid/run/7",
            }
        ]

    def status(self, repository):
        return {"repository": repository, "default_branch": "main"}

    def branch(self, repository, branch):
        return {"commit": {"sha": "abc"}}

    def latest_release(self, repository):
        return {
            "tag_name": "v1.2.3",
            "target_commitish": "abc",
            "published_at": "2026-09-28T00:02:00Z",
            "draft": False,
            "prerelease": False,
        }


def _role_gateway(tmp_path, monkeypatch, role):
    (tmp_path / "pyproject.toml").write_text(
        f"""
[project]
name = "demo"

[tool.gway.variables]
role = "{role}"
""".lstrip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    gateway = Gateway()
    gateway.security_path = tmp_path / "security.sqlite"
    gateway.wrap(
        "wire.check",
        lambda *, mutate=False: {"ready": True},
        op="check",
        sub="wire",
    )
    gateway.wrap(
        "log.search",
        lambda pattern, *source, since=None, until=None, limit=100, all=False, mutate=False: (
            []
        ),
        op="search",
        sub="log",
    )
    return gateway


def test_watch_zero_argument_snapshot_has_stable_sections(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    result = gateway.execute("watch", mutate=False)

    assert set(result) == EXPECTED_SECTIONS
    assert result["node"]["status"] == "ok"
    assert result["services"]["status"] == "ok"
    assert result["deploy"]["status"] == "unavailable"
    assert result["release"]["status"] == "unavailable"
    assert result["queue"]["status"] == "unavailable"
    assert result["wire"]["status"] == "ok"
    assert result["errors"]["status"] == "ok"
    assert result["changed_at"] is None
    assert result["cursor"] is None
    assert result["health"]["status"] == "ok"
    assert result["health"]["sections"]["deploy"] == "unavailable"
    assert gateway.ops.resolve("watch").mutates is False


def test_watch_degrades_one_failed_section_without_losing_snapshot(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    def fail(*, mutate=False):
        raise ConnectionError("wire offline")

    gateway.wrap("wire.check", fail, op="check", sub="wire")

    result = gateway("watch")

    assert set(result) == EXPECTED_SECTIONS
    assert result["wire"]["status"] == "error"
    assert result["wire"]["error"] == {
        "type": "ConnectionError",
        "message": "wire offline",
    }
    assert result["node"]["status"] == "ok"
    assert result["health"]["status"] == "degraded"
    assert result["health"]["degraded"] == ["wire"]


def test_watch_watchtower_sections_use_role_owned_observations(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "watchtower")
    gateway._github_controller = FakeGitHub()

    result = gateway("watch")

    assert result["deploy"]["status"] == "ok"
    assert result["release"]["status"] == "ok"
    assert result["queue"]["status"] == "ok"
    assert result["deploy"]["result"][0]["run_id"] == 7
    assert result["release"]["result"][0]["release_tag"] == "v1.2.3"
    assert result["queue"]["result"][0]["clear"] is True
    assert result["health"]["status"] == "ok"


def test_watch_error_search_is_bounded(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")
    calls = []

    def search(
        pattern,
        *source,
        since=None,
        until=None,
        limit=100,
        all=False,
        mutate=False,
    ):
        calls.append(
            {
                "pattern": pattern,
                "source": source,
                "limit": limit,
                "all": all,
                "mutate": mutate,
            }
        )
        return []

    gateway.wrap("log.search", search, op="search", sub="log")

    gateway("watch")

    assert calls == [
        {
            "pattern": "ERROR|CRITICAL",
            "source": (),
            "limit": 20,
            "all": True,
            "mutate": False,
        }
    ]


def test_watch_help_uses_first_class_recipe_documentation(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    general = gateway("help watch --verbose")
    errors = gateway("help watch errors")

    assert "Build a bounded structured snapshot" in general
    assert "Examples:" in general
    assert "At most 20 recent ERROR or CRITICAL log records" in errors


def test_watch_omits_sections_outside_external_authority(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "watchtower")
    gateway._github_controller = FakeGitHub()

    with gateway.authorized(
        operations={
            "watch",
            "node",
            "service.statuses",
        }
    ):
        result = gateway("watch")

    assert set(result) == {
        "node",
        "health",
        "services",
        "changed_at",
        "cursor",
    }
    assert result["node"]["status"] == "ok"
    assert result["services"]["status"] == "ok"
    assert result["health"]["status"] == "ok"
    assert result["health"]["sections"] == {
        "node": "ok",
        "services": "ok",
    }
    assert "deploy" not in result
    assert "release" not in result
    assert "queue" not in result
    assert "wire" not in result
    assert "errors" not in result


def test_watch_keeps_authorized_but_unavailable_sections(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    with gateway.authorized(
        operations={
            "watch",
            "node",
            "service.statuses",
            "wire.check",
            "log.search",
        }
    ):
        result = gateway("watch")

    assert result["node"]["status"] == "ok"
    assert result["services"]["status"] == "ok"
    assert result["wire"]["status"] == "ok"
    assert result["errors"]["status"] == "ok"
    assert result["deploy"]["status"] == "unavailable"
    assert result["release"]["status"] == "unavailable"
    assert result["queue"]["status"] == "unavailable"
    assert result["health"]["status"] == "ok"


def test_watch_scope_narrows_bound_caller_authority(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "watchtower")
    gateway._github_controller = FakeGitHub()
    scopes = ScopeRegistry(gateway.security_path)
    scopes.replace(
        "basic",
        operations={"node", "service.statuses"},
        environment=(),
    )

    with gateway.authorized(
        operations={
            "watch",
            "node",
            "service.statuses",
            "node.watchtower.deploy.status",
            "node.watchtower.release.status",
            "node.watchtower.queue.status",
            "wire.check",
            "log.search",
        },
        scopes={"basic"},
    ):
        original = gateway.authorization
        result = gateway("watch --scope basic")
        assert gateway.authorization is original

    assert set(result) == {
        "node",
        "health",
        "services",
        "changed_at",
        "cursor",
    }
    assert result["health"]["sections"] == {
        "node": "ok",
        "services": "ok",
    }


def test_watch_scope_cannot_add_grants_missing_from_caller(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "watchtower")
    gateway._github_controller = FakeGitHub()
    scopes = ScopeRegistry(gateway.security_path)
    scopes.replace(
        "broader",
        operations={
            "node",
            "service.statuses",
            "node.watchtower.deploy.status",
            "log.search",
        },
        environment=(),
    )

    with gateway.authorized(
        operations={"watch", "node"},
        scopes={"broader"},
    ):
        result = gateway("watch --scope broader")

    assert set(result) == {
        "node",
        "health",
        "changed_at",
        "cursor",
    }
    assert result["node"]["status"] == "ok"
    assert result["health"]["sections"] == {"node": "ok"}


def test_watch_scope_with_wildcard_caller_reduces_to_named_scope(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "watchtower")
    gateway._github_controller = FakeGitHub()
    ScopeRegistry(gateway.security_path).replace(
        "basic",
        operations={"node", "service.statuses"},
        environment=(),
    )

    with gateway.authorized(
        operations={"__all__"},
        environment={"__all__"},
        scopes={"basic"},
    ):
        result = gateway("watch --scope basic")

    assert set(result) == {
        "node",
        "health",
        "services",
        "changed_at",
        "cursor",
    }


def test_watch_scope_rejects_scope_not_visible_to_caller(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")
    ScopeRegistry(gateway.security_path).replace(
        "private",
        operations={"node"},
        environment=(),
    )

    with gateway.authorized(
        operations={"watch", "node"},
        scopes={"other"},
    ):
        with pytest.raises(
            AuthorizationError,
            match="Security scope is not available",
        ):
            gateway("watch --scope private")


def test_watch_scope_help_explains_narrowing_only(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    output = gateway("help watch --scope")

    assert "Narrow watch authority" in output
    assert "never add operation or environment grants" in output


def test_watch_only_reduces_visible_sections_and_health(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    result = gateway("watch --only node,services")

    assert set(result) == {
        "node",
        "services",
        "health",
        "changed_at",
        "cursor",
    }
    assert result["health"]["sections"] == {
        "node": "ok",
        "services": "ok",
    }


def test_watch_except_removes_sections_and_recomputes_health(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    def fail(*, mutate=False):
        raise ConnectionError("wire offline")

    gateway.wrap("wire.check", fail, op="check", sub="wire")

    unfiltered = gateway("watch")
    filtered = gateway("watch --except wire")

    assert unfiltered["health"]["status"] == "degraded"
    assert "wire" not in filtered
    assert filtered["health"]["status"] == "ok"
    assert "wire" not in filtered["health"]["sections"]


def test_watch_filters_cannot_restore_unauthorized_sections(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "watchtower")
    gateway._github_controller = FakeGitHub()

    with gateway.authorized(
        operations={"watch", "node"},
    ):
        result = gateway("watch --only node,services,deploy")

    assert set(result) == {
        "node",
        "health",
        "changed_at",
        "cursor",
    }
    assert result["health"]["sections"] == {"node": "ok"}


def test_watch_rejects_only_and_except_together(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    with pytest.raises(ValueError, match="only one of --only or --except"):
        gateway("watch --only node --except wire")


def test_watch_rejects_unknown_filter_section(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    with pytest.raises(ValueError, match="Unknown observation section"):
        gateway("watch --only mystery")


def test_watch_filter_help_documents_section_reduction(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    only = gateway("help watch --only")
    except_ = gateway("help watch --except")

    assert "Include selected watch sections" in only
    assert "comma-separated section list" in only
    assert "Exclude selected watch sections" in except_
    assert "cannot be used together" in except_


def test_watch_since_is_forwarded_to_bounded_error_search(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")
    calls = []

    def search(
        pattern,
        *source,
        since=None,
        until=None,
        limit=100,
        all=False,
        mutate=False,
    ):
        calls.append(
            {
                "pattern": pattern,
                "since": since,
                "limit": limit,
                "all": all,
                "mutate": mutate,
            }
        )
        return []

    gateway.wrap("log.search", search, op="search", sub="log")

    gateway('watch --since "10 minutes ago"')

    assert calls == [
        {
            "pattern": "ERROR|CRITICAL",
            "since": "10 minutes ago",
            "limit": 20,
            "all": True,
            "mutate": False,
        }
    ]


def test_watch_errors_keeps_only_problematic_sections(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    def fail(*, mutate=False):
        raise ConnectionError("wire offline")

    gateway.wrap("wire.check", fail, op="check", sub="wire")

    result = gateway("watch --errors")

    assert set(result) == {
        "wire",
        "health",
        "changed_at",
        "cursor",
    }
    assert result["wire"]["status"] == "error"
    assert result["health"]["status"] == "degraded"
    assert result["health"]["sections"] == {"wire": "error"}


def test_watch_errors_includes_nonempty_recent_error_logs(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    gateway.wrap(
        "log.search",
        lambda pattern, *source, since=None, until=None, limit=100, all=False, mutate=False: [
            {"message": "ERROR example"}
        ],
        op="search",
        sub="log",
    )

    result = gateway("watch --errors")

    assert set(result) == {
        "errors",
        "health",
        "changed_at",
        "cursor",
    }
    assert result["errors"]["status"] == "ok"
    assert result["errors"]["result"] == [{"message": "ERROR example"}]
    assert result["health"]["status"] == "ok"


def test_watch_errors_composes_after_only_filter(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    def fail(*, mutate=False):
        raise ConnectionError("wire offline")

    gateway.wrap("wire.check", fail, op="check", sub="wire")

    result = gateway("watch --only node,wire --errors")

    assert set(result) == {
        "wire",
        "health",
        "changed_at",
        "cursor",
    }


def test_watch_changed_fails_before_observation_work(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")
    calls = []

    gateway.wrap(
        "wire.check",
        lambda *, mutate=False: calls.append("wire"),
        op="check",
        sub="wire",
    )

    with pytest.raises(
        NotImplementedError,
        match="requires cursor/change tracking",
    ):
        gateway("watch --changed")

    assert calls == []


def test_watch_time_error_change_help(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    since = gateway("help watch --since")
    errors = gateway("help watch --errors")
    changed = gateway("help watch --changed")

    assert "Bound time-aware observations" in since
    assert "10 minutes ago" in since
    assert "Show only problematic observations" in errors
    assert "Optional unavailable capabilities are not treated as errors" in errors
    assert "Show only changed observations" in changed
    assert "requires a comparison cursor" in changed
