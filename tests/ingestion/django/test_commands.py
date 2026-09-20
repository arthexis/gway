import gway.ingestion.django as django_ingestor
from gway.ingestion.base import find_ingested


def test_unnamed_django_mount_does_not_index_management_commands(
    gateway,
    django_project,
    django_setup,
    django_management,
):
    root, _ = django_project()
    django_setup()
    django_management()

    mount = django_ingestor.ingest_project(gateway, root)

    assert mount.management_enabled is False
    assert find_ingested(gateway, ("arthexis",)) is None
    assert django_ingestor.ingest_commands(gateway, mount) == []
    assert gateway.ops.resolve("migrate") is None


def test_named_mount_expands_management_commands_on_first_project_subject_use(
    gateway,
    django_project,
    django_setup,
    django_management,
):
    root, _ = django_project()
    django_setup()
    calls = django_management()

    django_ingestor.ingest_project(gateway, root, name="arthexis")

    assert gateway.ops.resolve("arthexis.migrate") is None

    result = gateway("migrate arthexis --database default")

    assert result == {
        "command": "migrate",
        "args": (),
        "options": {"database": "default"},
    }
    assert calls == [
        ("migrate", (), {"database": "default"}),
    ]
    assert gateway.ops.resolve("arthexis.migrate") is not None


def test_management_commands_are_not_exposed_as_bare_top_level_operations(
    gateway,
    django_project,
    django_setup,
    django_management,
):
    root, _ = django_project()
    django_setup()
    django_management()

    django_ingestor.ingest_project(gateway, root, name="arthexis")
    gateway("migrate arthexis")

    assert gateway.ops.resolve("migrate") is None
    assert gateway.ops.resolve_pair("migrate", "arthexis") is not None
    assert gateway.ops.resolve("arthexis.migrate") is not None


def test_management_command_passes_positionals_and_boolean_flags_to_django(
    gateway,
    django_project,
    django_setup,
    django_management,
):
    root, _ = django_project()
    django_setup()
    calls = django_management()

    django_ingestor.ingest_project(gateway, root, name="arthexis")

    result = gateway("rebuild search arthexis index-a --force")

    assert result == {
        "command": "rebuild_search",
        "args": ("index-a",),
        "options": {"force": True},
    }
    assert calls[-1] == (
        "rebuild_search",
        ("index-a",),
        {"force": True},
    )


def test_management_command_metadata_identifies_project_and_command(
    gateway,
    django_project,
    django_setup,
    django_management,
):
    root, _ = django_project()
    django_setup()
    django_management()

    django_ingestor.ingest_project(gateway, root, name="arthexis")
    gateway("collectstatic arthexis")

    operation = gateway.ops.resolve("arthexis.collectstatic")
    assert operation.__gway_source_kind__ == "django-command"
    assert operation.__gway_subject__ == "arthexis"
    assert operation.__gway_metadata__["project"] == "arthexis"
    assert operation.__gway_metadata__["command"] == "collectstatic"


def test_management_command_expansion_is_idempotent(
    gateway,
    django_project,
    django_setup,
    monkeypatch,
):
    root, _ = django_project()
    django_setup()
    discoveries = []

    def get_commands():
        discoveries.append(True)
        return {"migrate": "django.core"}

    def call_command(name, *args, **options):
        return name

    monkeypatch.setattr(
        django_ingestor,
        "_management_api",
        lambda: (get_commands, call_command),
    )

    django_ingestor.ingest_project(gateway, root, name="arthexis")

    assert gateway("migrate arthexis") == "migrate"
    assert gateway("migrate arthexis") == "migrate"
    assert discoveries == [True]


def test_adding_name_to_existing_mount_indexes_management_subject(
    gateway,
    django_project,
    django_setup,
    django_management,
):
    root, _ = django_project()
    django_setup()
    django_management()

    mount = django_ingestor.ingest_project(gateway, root)
    assert find_ingested(gateway, ("arthexis",)) is None

    same_mount = django_ingestor.ingest_project(
        gateway,
        root,
        name="arthexis",
    )

    assert same_mount is mount
    command = find_ingested(gateway, ("migrate", "arthexis"))
    assert command is not None
    assert command.value.mount is mount
    assert command.value.name == "migrate"
    assert gateway("migrate arthexis")["command"] == "migrate"
