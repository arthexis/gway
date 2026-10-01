"""Architecture contracts for the sampler-owned GitHub capability."""

import importlib.util

from sampler.github import Controller
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


def test_legacy_github_controller_module_is_removed():
    assert importlib.util.find_spec("sampler.github._legacy") is None


def test_admin_operations_are_owned_by_extracted_admin_domains():
    allowed = {
        "sampler.github.admin_rulesets",
        "sampler.github.admin_protection",
        "sampler.github.admin_access",
        "sampler.github.admin_actions_policy",
    }

    assert {
        getattr(getattr(Controller, name), "__module__", None)
        for name in ADMIN_OPERATIONS
    } <= allowed


def test_composite_controller_has_no_legacy_backed_public_operations():
    assert all(
        getattr(getattr(Controller, name), "__module__", None)
        != "sampler.github._legacy"
        for name in dir(Controller)
        if not name.startswith("_") and callable(getattr(Controller, name))
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
