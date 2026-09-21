def test_github_shorthand_routes_through_git_materialization(
    gateway,
    tmp_path,
    monkeypatch,
):
    import gway.install.git as git_source

    materialized = tmp_path / "materialized"
    materialized.mkdir()
    (materialized / "pyproject.toml").write_text(
        "[project]\nname = 'gway'\n",
        encoding="utf-8",
    )
    (materialized / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    seen = {}

    def fake_materialize(source, *, ref=None, cache=None):
        seen["source"] = source
        seen["ref"] = ref
        return git_source.GitArtifact(
            source="https://github.com/arthexis/gway.git",
            requested_ref=ref,
            resolved_revision="a" * 40,
            path=materialized,
        )

    monkeypatch.setattr(git_source, "materialize", fake_materialize)

    installed = gateway("install arthexis/gway --ref main")

    assert seen == {
        "source": "arthexis/gway",
        "ref": "main",
    }
    assert installed.source == "https://github.com/arthexis/gway.git"
    assert installed.requested_ref == "main"
    assert installed.resolved_revision == "a" * 40
