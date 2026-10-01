import pytest

import gway.security.django_publication as publication
from gway.security.django_publication import (
    collect_django_publications,
    derive_django_publications,
)

from .django_scope_harness import DjangoScopeHarness, UNSET


@pytest.fixture
def django_scope(tmp_path):
    return DjangoScopeHarness(tmp_path)


@pytest.mark.parametrize("app_label", ["widgets", "gadgets"])
def test_scope_identity_is_derived_from_product_and_app(tmp_path, app_label):
    harness = DjangoScopeHarness(tmp_path, app_label=app_label)
    harness.records(
        harness.operation(harness.app, f"{app_label}.list", mutates=False),
    )

    scope = harness.scopes()[f"demo-{app_label}-read"]

    assert scope.semantic_terms == frozenset({"demo", app_label, "read"})
    assert scope.source == f"django:demo:{app_label}"


@pytest.mark.parametrize(
    ("mutates", "expected_leaf"),
    [
        (False, "demo-widgets-read"),
        (True, "demo-widgets-write"),
        (UNSET, "demo-widgets-write"),
    ],
)
def test_mutation_contract_selects_authority_leaf(
    django_scope,
    mutates,
    expected_leaf,
):
    django_scope.records(
        django_scope.operation(django_scope.app, "widgets.operation", mutates=mutates),
    )

    scopes = django_scope.scopes()

    assert list(scopes) == [expected_leaf]
    assert scopes[expected_leaf].operations == frozenset({"widgets.operation"})


def test_read_and_write_operations_are_partitioned_without_overlap(django_scope):
    django_scope.records(
        django_scope.operation(django_scope.app, "widgets.list", mutates=False),
        django_scope.operation(django_scope.app, "widgets.create", mutates=True),
    )

    scopes = django_scope.scopes()

    assert set(scopes) == {"demo-widgets-read", "demo-widgets-write"}
    assert scopes["demo-widgets-read"].operations == frozenset({"widgets.list"})
    assert scopes["demo-widgets-write"].operations == frozenset({"widgets.create"})


def test_non_django_operation_never_enters_django_authority(django_scope):
    django_scope.records(
        django_scope.operation(
            django_scope.app,
            "widgets.list",
            mutates=False,
            kind="python-callable",
        ),
    )

    assert django_scope.scopes() == {}


def test_app_outside_project_root_does_not_publish_authority(django_scope, tmp_path):
    framework_app = django_scope.external_app(
        tmp_path / "site-packages" / "django" / "contrib"
    )
    django_scope.records(
        django_scope.operation(framework_app, "auth.list", mutates=False),
    )

    assert django_scope.scopes() == {}


@pytest.mark.parametrize(
    ("command", "mutates", "leaf"),
    [
        ("inspect_widgets", False, "demo-widgets-read"),
        ("sync_widgets", True, "demo-widgets-write"),
        ("unknown_widgets", UNSET, "demo-widgets-write"),
    ],
)
def test_management_command_uses_owned_app_and_mutation_contract(
    django_scope,
    monkeypatch,
    command,
    mutates,
    leaf,
):
    django_scope.records(django_scope.command(command, mutates=mutates))
    monkeypatch.setattr(
        publication,
        "_command_sources",
        lambda: {command: django_scope.app.name},
    )

    scopes = django_scope.scopes()

    assert list(scopes) == [leaf]
    assert scopes[leaf].operations == frozenset({f"demo.{command}"})


def test_management_command_without_owned_app_provenance_publishes_nothing(
    django_scope,
    monkeypatch,
):
    django_scope.records(django_scope.command("migrate", mutates=True))
    monkeypatch.setattr(
        publication,
        "_command_sources",
        lambda: {"migrate": "django.core"},
    )

    assert django_scope.scopes() == {}


def test_collect_retires_stale_django_scopes_and_preserves_manual_publications(
    django_scope,
):
    django_scope.gateway._published_scopes = {
        "manual-read": {
            "source": "demo",
            "operations": frozenset({"manual.list"}),
            "semantic_terms": frozenset({"manual", "read"}),
        },
        "demo-old-read": {
            "source": "django:demo:old",
            "operations": frozenset({"old.list"}),
            "semantic_terms": frozenset({"demo", "old", "read"}),
        },
    }
    django_scope.records(
        django_scope.operation(django_scope.app, "widgets.list", mutates=False),
    )

    published = collect_django_publications(django_scope.gateway)

    assert set(published) == {"manual-read", "demo-widgets-read"}
    assert published["demo-widgets-read"]["semantic_terms"] == frozenset(
        {"demo", "widgets", "read"}
    )


@pytest.mark.parametrize("has_registry", [False, True])
def test_no_discovered_operations_publish_no_authority(tmp_path, has_registry):
    harness = DjangoScopeHarness(tmp_path)
    if not has_registry:
        del harness.gateway.ops

    assert derive_django_publications(harness.gateway) == ()
