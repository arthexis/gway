from gway import Gateway


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
