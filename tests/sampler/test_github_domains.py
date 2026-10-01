"""Architecture checks for the sampler-owned GitHub domain split."""

from sampler.github.checks import Controller


def test_github_controller_methods_are_owned_by_domain_modules():
    expected = {
        "repository": "sampler.github.repository",
        "pull": "sampler.github.pulls",
        "issue": "sampler.github.issues",
        "review_threads": "sampler.github.reviews",
        "runs": "sampler.github.actions",
        "release": "sampler.github.releases",
        "check_ci": "sampler.github.checks",
    }

    for name, module in expected.items():
        assert getattr(Controller, name).__module__ == module


def test_github_composite_keeps_admin_as_the_only_legacy_slice():
    assert Controller.rulesets.__module__ == "sampler.github._legacy"
    assert Controller.branch_protection.__module__ == "sampler.github._legacy"

    non_admin = {
        "repository",
        "pull",
        "issue",
        "review_threads",
        "runs",
        "release",
        "set_secret",
    }
    assert all(
        getattr(Controller, name).__module__ != "sampler.github._legacy"
        for name in non_admin
    )
