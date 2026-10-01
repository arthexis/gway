"""Architecture contracts for the sampler-owned GitHub capability."""

import inspect

from sampler.github import Controller
from sampler.github._legacy import Controller as LegacyController
from sampler.github.admin import ADMIN_OPERATIONS


def test_public_surface_is_owned_by_expected_domain_layers():
    expected = {
        "repository": "sampler.github.repository",
        "pull": "sampler.github.pulls",
        "issue": "sampler.github.issues",
        "review_threads": "sampler.github.reviews",
        "runs": "sampler.github.actions",
        "release": "sampler.github.releases",
        "check_ci": "sampler.github.checks",
        "observe_ci": "sampler.github.observe",
        "check_rollout": "sampler.github.rollout",
        "status": "sampler.github.status",
        "rulesets": "sampler.github.admin_rulesets",
        "branch_protection": "sampler.github.admin_protection",
        "collaborators": "sampler.github.admin_access",
        "actions_permissions": "sampler.github.admin_actions_policy",
    }

    assert {
        name: getattr(Controller, name).__module__ for name in expected
    } == expected


def test_composite_controller_has_no_legacy_backed_public_operations():
    legacy_public = {
        name
        for name in dir(Controller)
        if not name.startswith("_")
        and callable(getattr(Controller, name))
        and getattr(getattr(Controller, name), "__module__", None)
        == "sampler.github._legacy"
    }

    assert legacy_public == set()


def test_extracted_admin_signatures_match_legacy_contract():
    for name in ADMIN_OPERATIONS:
        assert inspect.signature(getattr(Controller, name)) == inspect.signature(
            getattr(LegacyController, name)
        )


def test_non_admin_mutations_are_owned_by_domain_modules():
    expected = {
        "set_secret": "sampler.github.actions",
        "create_pull": "sampler.github.pulls",
        "comment_issue": "sampler.github.issues",
        "create_release": "sampler.github.releases",
        "create_branch": "sampler.github.repository",
    }

    assert {
        name: getattr(Controller, name).__module__ for name in expected
    } == expected
