import logging

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


def test_survey_zero_argument_snapshot_has_stable_sections(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    result = gateway.execute("survey", mutate=False)

    assert set(result) == EXPECTED_SECTIONS
    assert result["node"]["status"] == "ok"
    assert result["services"]["status"] == "ok"
    assert result["deploy"]["status"] == "unavailable"
    assert result["release"]["status"] == "unavailable"
    assert result["queue"]["status"] == "unavailable"
    assert result["wire"]["status"] == "ok"
    assert result["errors"]["status"] == "ok"
    assert result["changed_at"] is None
    assert isinstance(result["cursor"], str)
    assert result["cursor"]
    assert result["health"]["status"] == "ok"
    assert result["health"]["sections"]["deploy"] == "unavailable"
    assert gateway.ops.resolve("survey").mutates is False


def test_survey_degrades_one_failed_section_without_losing_snapshot(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    def fail(*, mutate=False):
        raise ConnectionError("wire offline")

    gateway.wrap("wire.check", fail, op="check", sub="wire")

    result = gateway("survey")

    assert set(result) == EXPECTED_SECTIONS
    assert result["wire"]["status"] == "error"
    assert result["wire"]["error"] == {
        "type": "ConnectionError",
        "message": "wire offline",
    }
    assert result["node"]["status"] == "ok"
    assert result["health"]["status"] == "degraded"
    assert result["health"]["degraded"] == ["wire"]


def test_survey_watchtower_sections_use_role_owned_observations(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "watchtower")
    gateway._github_controller = FakeGitHub()

    result = gateway("survey")

    assert result["deploy"]["status"] == "ok"
    assert result["release"]["status"] == "ok"
    assert result["queue"]["status"] == "ok"
    assert result["deploy"]["result"][0]["run_id"] == 7
    assert result["release"]["result"][0]["release_tag"] == "v1.2.3"
    assert result["queue"]["result"][0]["clear"] is True
    assert result["health"]["status"] == "ok"


def test_survey_error_search_is_bounded(tmp_path, monkeypatch):
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

    gateway("survey")

    assert calls == [
        {
            "pattern": "ERROR|CRITICAL",
            "source": (),
            "limit": 20,
            "all": True,
            "mutate": False,
        }
    ]


def test_survey_help_uses_first_class_recipe_documentation(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    general = gateway("help survey --verbose")
    errors = gateway("help survey errors")

    assert "Build a bounded structured snapshot" in general
    assert "Examples:" in general
    assert "At most 20 recent ERROR or CRITICAL log records" in errors


def test_survey_omits_sections_outside_external_authority(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "watchtower")
    gateway._github_controller = FakeGitHub()

    with gateway.authorized(
        operations={
            "survey",
            "node",
            "service.statuses",
        }
    ):
        result = gateway("survey")

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


def test_survey_keeps_authorized_but_unavailable_sections(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    with gateway.authorized(
        operations={
            "survey",
            "node",
            "service.statuses",
            "wire.check",
            "log.search",
        }
    ):
        result = gateway("survey")

    assert result["node"]["status"] == "ok"
    assert result["services"]["status"] == "ok"
    assert result["wire"]["status"] == "ok"
    assert result["errors"]["status"] == "ok"
    assert result["deploy"]["status"] == "unavailable"
    assert result["release"]["status"] == "unavailable"
    assert result["queue"]["status"] == "unavailable"
    assert result["health"]["status"] == "ok"


def test_survey_scope_narrows_bound_caller_authority(tmp_path, monkeypatch):
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
            "survey",
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
        result = gateway("survey --scope basic")
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


def test_survey_scope_cannot_add_grants_missing_from_caller(tmp_path, monkeypatch):
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
        operations={"survey", "node"},
        scopes={"broader"},
    ):
        result = gateway("survey --scope broader")

    assert set(result) == {
        "node",
        "health",
        "changed_at",
        "cursor",
    }
    assert result["node"]["status"] == "ok"
    assert result["health"]["sections"] == {"node": "ok"}


def test_survey_scope_with_wildcard_caller_reduces_to_named_scope(tmp_path, monkeypatch):
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
        result = gateway("survey --scope basic")

    assert set(result) == {
        "node",
        "health",
        "services",
        "changed_at",
        "cursor",
    }


def test_survey_scope_rejects_scope_not_visible_to_caller(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")
    ScopeRegistry(gateway.security_path).replace(
        "private",
        operations={"node"},
        environment=(),
    )

    with gateway.authorized(
        operations={"survey", "node"},
        scopes={"other"},
    ):
        with pytest.raises(
            AuthorizationError,
            match="Security scope is not available",
        ):
            gateway("survey --scope private")


def test_survey_scope_help_explains_narrowing_only(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    output = gateway("help survey --scope")

    assert "Narrow watch authority" in output
    assert "never add operation or environment grants" in output


def test_survey_only_reduces_visible_sections_and_health(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    result = gateway("survey --only node,services")

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


def test_survey_except_removes_sections_and_recomputes_health(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    def fail(*, mutate=False):
        raise ConnectionError("wire offline")

    gateway.wrap("wire.check", fail, op="check", sub="wire")

    unfiltered = gateway("survey")
    filtered = gateway("survey --except wire")

    assert unfiltered["health"]["status"] == "degraded"
    assert "wire" not in filtered
    assert filtered["health"]["status"] == "ok"
    assert "wire" not in filtered["health"]["sections"]


def test_survey_filters_cannot_restore_unauthorized_sections(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "watchtower")
    gateway._github_controller = FakeGitHub()

    with gateway.authorized(
        operations={"survey", "node"},
    ):
        result = gateway("survey --only node,services,deploy")

    assert set(result) == {
        "node",
        "health",
        "changed_at",
        "cursor",
    }
    assert result["health"]["sections"] == {"node": "ok"}


def test_survey_rejects_only_and_except_together(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    with pytest.raises(ValueError, match="only one of --only or --except"):
        gateway("survey --only node --except wire")


def test_survey_rejects_unknown_filter_section(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    with pytest.raises(ValueError, match="Unknown observation section"):
        gateway("survey --only mystery")


def test_survey_filter_help_documents_section_reduction(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    only = gateway("help survey --only")
    except_ = gateway("help survey --except")

    assert "Include selected watch sections" in only
    assert "comma-separated section list" in only
    assert "Exclude selected watch sections" in except_
    assert "cannot be used together" in except_


def test_survey_since_is_forwarded_to_bounded_error_search(tmp_path, monkeypatch):
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


def test_survey_problems_keeps_only_problematic_sections(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    def fail(*, mutate=False):
        raise ConnectionError("wire offline")

    gateway.wrap("wire.check", fail, op="check", sub="wire")

    result = gateway("survey --problems")

    assert set(result) == {
        "wire",
        "health",
        "changed_at",
        "cursor",
    }
    assert result["wire"]["status"] == "error"
    assert result["health"]["status"] == "degraded"
    assert result["health"]["sections"] == {"wire": "error"}


def test_survey_problems_includes_nonempty_recent_error_logs(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    gateway.wrap(
        "log.search",
        lambda pattern, *source, since=None, until=None, limit=100, all=False, mutate=False: [
            {"message": "ERROR example"}
        ],
        op="search",
        sub="log",
    )

    result = gateway("survey --problems")

    assert set(result) == {
        "errors",
        "health",
        "changed_at",
        "cursor",
    }
    assert result["errors"]["status"] == "ok"
    assert result["errors"]["result"] == [{"message": "ERROR example"}]
    assert result["health"]["status"] == "ok"


def test_survey_problems_composes_after_only_filter(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    def fail(*, mutate=False):
        raise ConnectionError("wire offline")

    gateway.wrap("wire.check", fail, op="check", sub="wire")

    result = gateway("survey --only node,wire --problems")

    assert set(result) == {
        "wire",
        "health",
        "changed_at",
        "cursor",
    }


def test_survey_changed_requires_cursor_before_observation_work(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")
    calls = []

    gateway.wrap(
        "wire.check",
        lambda *, mutate=False: calls.append("wire"),
        op="check",
        sub="wire",
    )

    with pytest.raises(ValueError, match="requires --cursor"):
        gateway("survey --changed")

    assert calls == []


def test_survey_time_error_change_help(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    since = gateway("help survey --since")
    problems = gateway("help survey --problems")
    changed = gateway("help survey --changed")

    assert "Bound time-aware observations" in since
    assert "10 minutes ago" in since
    assert "Show only problematic observations" in problems
    assert "Optional unavailable capabilities are not treated as errors" in problems
    assert "Show only changed observations" in changed
    assert "prior opaque cursor" in changed
    cursor = gateway("help survey --cursor")
    assert "Opaque versioned watch cursor" in cursor


def test_survey_cursor_is_stateless_and_unchanged_snapshot_returns_no_sections(
    tmp_path,
    monkeypatch,
):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")

    first = gateway("survey")
    second = gateway(f"survey --changed --cursor {first['cursor']}")

    assert set(second) == {"health", "changed_at", "cursor"}
    assert second["health"]["status"] == "ok"
    assert second["health"]["sections"] == {}
    assert second["changed_at"] is None
    assert isinstance(second["cursor"], str)
    assert second["cursor"]


def test_survey_changed_returns_only_modified_visible_section(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")
    state = {"ready": True}

    gateway.wrap(
        "wire.check",
        lambda *, mutate=False: {"ready": state["ready"]},
        op="check",
        sub="wire",
    )

    first = gateway("survey")
    state["ready"] = False
    second = gateway(f"survey --changed --cursor {first['cursor']}")

    assert set(second) == {
        "wire",
        "health",
        "changed_at",
        "cursor",
    }
    assert second["wire"]["result"] == {"ready": False}
    assert second["health"]["sections"] == {"wire": "ok"}
    assert second["changed_at"] is not None


def test_survey_changed_does_not_report_sections_lost_to_authority(
    tmp_path,
    monkeypatch,
):
    gateway = _role_gateway(tmp_path, monkeypatch, "watchtower")
    gateway._github_controller = FakeGitHub()

    with gateway.authorized(
        operations={
            "survey",
            "node",
            "service.statuses",
            "node.watchtower.deploy.status",
        }
    ):
        first = gateway("survey")

    with gateway.authorized(
        operations={"survey", "node"},
    ):
        second = gateway(f"survey --changed --cursor {first['cursor']}")

    assert "deploy" not in second
    assert "services" not in second


def test_survey_rejects_invalid_cursor_before_observation_work(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")
    calls = []

    gateway.wrap(
        "wire.check",
        lambda *, mutate=False: calls.append("wire"),
        op="check",
        sub="wire",
    )

    with pytest.raises(ValueError, match="Invalid observation cursor"):
        gateway("survey --changed --cursor not-a-valid-cursor")

    assert calls == []


def test_survey_changed_composes_with_only_filter(tmp_path, monkeypatch):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")
    state = {"ready": True}

    gateway.wrap(
        "wire.check",
        lambda *, mutate=False: {"ready": state["ready"]},
        op="check",
        sub="wire",
    )

    first = gateway("survey --only node,wire")
    state["ready"] = False
    second = gateway(
        f"survey --only node,wire --changed --cursor {first['cursor']}"
    )

    assert set(second) == {
        "wire",
        "health",
        "changed_at",
        "cursor",
    }


def test_timed_watch_reports_recipe_lifecycle_and_nested_operations(
    tmp_path,
    monkeypatch,
    caplog,
):
    gateway = _role_gateway(tmp_path, monkeypatch, "control")
    gateway.timed_enabled = True
    gateway.logger.setLevel(logging.INFO)

    with caplog.at_level(logging.INFO):
        result = gateway("survey --only node,wire")

    assert result["node"]["status"] == "ok"
    messages = [
        record.getMessage()
        for record in caplog.records
        if "[timed]" in record.getMessage()
    ]

    assert any("route sampler discovery" in message for message in messages)
    assert any("recipe watch load" in message for message in messages)
    assert any("recipe watch parse" in message for message in messages)
    assert any("recipe watch execute" in message for message in messages)
    assert any("operation node " in message for message in messages)
    assert any("operation wire.check " in message for message in messages)
    assert any("operation watch " in message for message in messages)


def test_timing_does_not_change_watch_structured_result(tmp_path, monkeypatch):
    plain = _role_gateway(tmp_path, monkeypatch, "control")
    plain_result = plain("survey --only node,wire")

    timed = _role_gateway(tmp_path, monkeypatch, "control")
    timed.timed_enabled = True
    timed_result = timed("survey --only node,wire")

    for result in (plain_result, timed_result):
        assert set(result) == {"node", "wire", "health", "changed_at", "cursor"}
        assert result["node"]["status"] == "ok"
        assert result["wire"]["status"] == "ok"
        assert result["health"]["status"] == "ok"
