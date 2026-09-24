from pathlib import Path


def test_gway_main_dispatches_watchtower_deploy_directly() -> None:
    workflow = Path(".github/workflows/watchtower-deploy-trigger.yml").read_text(
        encoding="utf-8"
    )

    assert "push:" in workflow
    assert "branches: [main]" in workflow
    assert "workflow_run:" not in workflow
    assert 'workflows: ["python / Python compatibility"]' not in workflow
    assert "schedule:" not in workflow
    assert "WATCHTOWER_DEPLOY_TOKEN: ${{ secrets.WATCHTOWER_DEPLOY_TOKEN }}" in workflow
    assert (
        "https://api.github.com/repos/arthexis/arthexis/actions/workflows/"
        "watchtower-deploy.yml/dispatches"
    ) in workflow
    assert '"ref":"main"' in workflow
    assert 'echo "watchtower_deploy=dispatched"' in workflow


def test_cross_repo_trigger_uses_only_explicit_secret() -> None:
    workflow = Path(".github/workflows/watchtower-deploy-trigger.yml").read_text(
        encoding="utf-8"
    )

    assert "github.token" not in workflow
    assert "repository_dispatch" not in workflow
    assert "actions: write" not in workflow
