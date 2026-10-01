"""Architecture contracts for the sampler-owned GitHub capability."""

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
    }

    assert {
        name: getattr(Controller, name).__module__ for name in expected
    } == expected


def test_legacy_implementation_is_reachable_only_through_admin_operations():
    legacy_public = {
        name
        for name in dir(Controller)
        if not name.startswith("_")
        and callable(getattr(Controller, name))
        and getattr(getattr(Controller, name), "__module__", None)
        == "sampler.github._legacy"
    }

    assert legacy_public == set(ADMIN_OPERATIONS)


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
