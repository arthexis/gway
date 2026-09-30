from pathlib import Path


def test_legacy_watchtower_deploy_trigger_is_manual_only() -> None:
    workflow = Path(".github/workflows/watchtower-deploy-trigger.yml").read_text(
        encoding="utf-8"
    )

    assert "workflow_dispatch:" in workflow
    assert "push:" not in workflow
    assert "branches: [main]" not in workflow
    assert "workflow_run:" not in workflow
    assert "schedule:" not in workflow
    assert "WATCHTOWER_DEPLOY_TOKEN: ${{ secrets.WATCHTOWER_DEPLOY_TOKEN }}" in workflow
    assert (
        "https://api.github.com/repos/arthexis/arthexis/actions/workflows/"
        "watchtower-deploy.yml/dispatches"
    ) in workflow
    assert '"ref":"main"' in workflow
    assert 'echo "watchtower_deploy=dispatched"' in workflow


def test_automatic_watchtower_candidate_flow_classifies_main_pushes() -> None:
    workflow = Path(".github/workflows/watchtower-candidate.yml").read_text(
        encoding="utf-8"
    )

    assert "push:" in workflow
    assert "branches: [main]" in workflow
    assert "Detect version-only rollover" in workflow
    assert 'print("false" if version_only else "true")' in workflow
    assert "if: needs.classify.outputs.deploy == 'true'" in workflow
    assert "event_type='gway-candidate'" in workflow
    assert 'grep -Fxq deploy <<<"$labels"' not in workflow
    assert "force_deploy" not in workflow
    assert "timing: ${{ steps.change.outputs.timing }}" in workflow
    assert 'client_payload[timing]="$TIMING"' in workflow
    assert "default: queued" in workflow
    assert "- immediate" in workflow
    assert "default: 2-remote" in workflow
    assert "- 0-gway" in workflow
    assert "- 1-arthexis" in workflow
    assert "- 2-remote" in workflow
    assert "- 3-release" in workflow
    assert "remote-only" not in workflow


def test_cross_repo_trigger_uses_only_explicit_secret() -> None:
    workflow = Path(".github/workflows/watchtower-deploy-trigger.yml").read_text(
        encoding="utf-8"
    )

    assert "github.token" not in workflow
    assert "repository_dispatch" not in workflow
    assert "actions: write" not in workflow
