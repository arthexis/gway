from pathlib import Path


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


def test_github_maintenance_purges_retired_workflow_history() -> None:
    workflow = Path(".github/workflows/github-maintenance.yml").read_text(
        encoding="utf-8"
    )

    assert "actions: write" in workflow
    assert "purge-retired-workflows:" in workflow
    assert '"watchtower-deploy-trigger.yml"' in workflow
    assert "actions/workflows?per_page=100" in workflow
    assert "actions/runs/$run_id" in workflow
    assert 'DRY_RUN: ${{ inputs.dry_run }}' in workflow
