from pathlib import Path
from types import SimpleNamespace

import pytest

import gway.ingestion.django as django_ingestor
from gway.ingestion.base import find_ingested


def _model(name):
    return type(
        name.title(),
        (),
        {"_meta": SimpleNamespace(model_name=name)},
    )


def _app(label, models):
    return SimpleNamespace(
        label=label,
        get_models=lambda: list(models),
    )


def _project(tmp_path, settings="demo.settings"):
    root = tmp_path / "project"
    root.mkdir()
    manage = root / "manage.py"
    manage.write_text(
        "import os\n"
        f"os.environ.setdefault('DJANGO_SETTINGS_MODULE', {settings!r})\n",
        encoding="utf-8",
    )
    return root, manage


def test_manage_path_is_recognized_as_django_project(tmp_path):
    root, manage = _project(tmp_path)

    assert django_ingestor.is_project_path(manage)
    assert django_ingestor.is_project_path(root)


def test_project_mount_discovers_settings_from_manage_and_indexes_apps_models(
    gateway,
    tmp_path,
    monkeypatch,
):
    root, _ = _project(tmp_path)
    charger = _model("charger")
    customer = _model("customer")
    registry = SimpleNamespace(
        get_app_configs=lambda: (
            _app("energy", [charger]),
            _app("sales", [customer]),
        ),
    )
    seen = {}

    def fake_setup(project_root, *, settings=None):
        seen["root"] = Path(project_root)
        seen["settings"] = settings
        return registry

    monkeypatch.setattr(django_ingestor, "_setup_project", fake_setup)

    mount = django_ingestor.ingest_project(gateway, root)

    assert mount.root == root.resolve()
    assert mount.settings == "demo.settings"
    assert mount.name is None
    assert mount.management_enabled is False
    assert seen == {"root": root.resolve(), "settings": "demo.settings"}

    assert find_ingested(gateway, ("energy",)).value.label == "energy"
    assert find_ingested(gateway, ("energy", "charger")).value is charger
    assert find_ingested(gateway, ("charger",)).value is charger
    assert find_ingested(gateway, ("sales", "customer")).value is customer
    assert find_ingested(gateway, ("customer",)).value is customer


def test_duplicate_model_names_do_not_get_ambiguous_short_branch(
    gateway,
    tmp_path,
    monkeypatch,
):
    root, _ = _project(tmp_path)
    energy_charger = _model("charger")
    legacy_charger = _model("charger")
    registry = SimpleNamespace(
        get_app_configs=lambda: (
            _app("energy", [energy_charger]),
            _app("legacy", [legacy_charger]),
        ),
    )
    monkeypatch.setattr(
        django_ingestor,
        "_setup_project",
        lambda *args, **kwargs: registry,
    )

    django_ingestor.ingest_project(gateway, root)

    assert find_ingested(gateway, ("energy", "charger")).value is energy_charger
    assert find_ingested(gateway, ("legacy", "charger")).value is legacy_charger
    assert find_ingested(gateway, ("charger",)) is None


def test_named_project_mount_authorizes_later_management_command_ingestion(
    gateway,
    tmp_path,
    monkeypatch,
):
    root, _ = _project(tmp_path)
    registry = SimpleNamespace(get_app_configs=lambda: ())
    monkeypatch.setattr(
        django_ingestor,
        "_setup_project",
        lambda *args, **kwargs: registry,
    )
    _management_fixture(monkeypatch)

    mount = django_ingestor.ingest_project(gateway, root, name="arthexis")

    assert mount.name == "arthexis"
    assert mount.management_enabled is True
    assert gateway.ops.resolve("migrate") is None


def test_reingesting_unnamed_project_can_add_project_name(
    gateway,
    tmp_path,
    monkeypatch,
):
    root, _ = _project(tmp_path)
    registry = SimpleNamespace(get_app_configs=lambda: ())
    monkeypatch.setattr(
        django_ingestor,
        "_setup_project",
        lambda *args, **kwargs: registry,
    )
    _management_fixture(monkeypatch)

    first = django_ingestor.ingest_project(gateway, root)
    second = django_ingestor.ingest_project(gateway, root, name="arthexis")

    assert second is first
    assert first.name == "arthexis"
    assert first.management_enabled is True


def test_reingesting_named_project_with_different_name_is_rejected(
    gateway,
    tmp_path,
    monkeypatch,
):
    root, _ = _project(tmp_path)
    registry = SimpleNamespace(get_app_configs=lambda: ())
    monkeypatch.setattr(
        django_ingestor,
        "_setup_project",
        lambda *args, **kwargs: registry,
    )
    _management_fixture(monkeypatch)

    django_ingestor.ingest_project(gateway, root, name="first")

    with pytest.raises(ValueError, match="already mounted"):
        django_ingestor.ingest_project(gateway, root, name="second")


def test_settings_module_source_can_mount_django_without_manage_py(
    gateway,
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    registry = SimpleNamespace(get_app_configs=lambda: ())
    seen = {}

    def fake_setup(root, *, settings=None):
        seen["root"] = Path(root)
        seen["settings"] = settings
        return registry

    monkeypatch.setattr(django_ingestor, "_setup_project", fake_setup)
    _management_fixture(monkeypatch)

    mount = django_ingestor.ingest_project(
        gateway,
        "project.settings",
        name="project",
    )

    assert mount.settings == "project.settings"
    assert mount.name == "project"
    assert seen == {
        "root": tmp_path.resolve(),
        "settings": "project.settings",
    }


def test_missing_django_dependency_has_clear_error(monkeypatch):
    real_import = django_ingestor.import_module

    def fake_import(name):
        if name == "django":
            raise ModuleNotFoundError("No module named 'django'", name="django")
        return real_import(name)

    monkeypatch.setattr(django_ingestor, "import_module", fake_import)

    with pytest.raises(ModuleNotFoundError, match="requires Django"):
        django_ingestor._load_django()



class _FakeModelBase:
    pass


class _FakeManagerBase:
    pass


def _orm_fixture():
    class Charger(_FakeModelBase):
        _meta = SimpleNamespace(
            app_label="energy",
            model_name="charger",
        )

        @classmethod
        def describe(cls):
            return "charger-model"

        def save(self):
            return self

        def custom(self, value):
            return f"{self.serial}:{value}"

        def __init__(self, serial="ABC"):
            self.serial = serial

    class ChargerManager(_FakeManagerBase):
        model = Charger

        def all(self):
            return ["all"]

        def filter(self, **criteria):
            return criteria

        def create(self, **values):
            return Charger(**values)

    manager = ChargerManager()
    Charger._default_manager = manager
    return Charger, manager


def test_direct_model_ingestion_exposes_manager_operations_on_model_subject(
    gateway,
    monkeypatch,
):
    Charger, _ = _orm_fixture()
    monkeypatch.setattr(
        django_ingestor,
        "_django_types",
        lambda: (_FakeModelBase, _FakeManagerBase),
    )

    gateway.ingest(Charger)

    assert gateway("filter charger --status online") == {"status": "online"}
    operation = gateway.ops.resolve("energy.charger.filter")
    assert operation is not None
    assert operation.__gway_source_kind__ == "django-manager"
    assert operation.__gway_subject__ == "charger"


def test_direct_model_ingestion_exposes_class_methods_on_model_subject(
    gateway,
    monkeypatch,
):
    Charger, _ = _orm_fixture()
    monkeypatch.setattr(
        django_ingestor,
        "_django_types",
        lambda: (_FakeModelBase, _FakeManagerBase),
    )

    gateway.ingest(Charger)

    assert gateway("describe charger") == "charger-model"
    assert gateway.ops.resolve("energy.charger.describe") is not None


def test_direct_manager_ingestion_infers_its_model_subject(
    gateway,
    monkeypatch,
):
    _, manager = _orm_fixture()
    monkeypatch.setattr(
        django_ingestor,
        "_django_types",
        lambda: (_FakeModelBase, _FakeManagerBase),
    )

    gateway.ingest(manager)

    assert gateway("all charger") == ["all"]
    assert gateway.ops.resolve("energy.charger.all") is not None


def test_direct_model_instance_ingestion_exposes_bound_methods_and_context(
    gateway,
    monkeypatch,
):
    Charger, _ = _orm_fixture()
    monkeypatch.setattr(
        django_ingestor,
        "_django_types",
        lambda: (_FakeModelBase, _FakeManagerBase),
    )
    charger = Charger("CHG001")

    gateway.ingest(charger)

    assert gateway.context["charger"] is charger
    assert gateway("custom charger test") == "CHG001:test"
    assert gateway.ops.resolve("energy.charger.custom") is not None


def test_project_indexed_model_expands_manager_surface_on_first_resolution(
    gateway,
    tmp_path,
    monkeypatch,
):
    root, _ = _project(tmp_path)
    Charger, _ = _orm_fixture()
    app = _app("energy", [Charger])
    registry = SimpleNamespace(get_app_configs=lambda: (app,))

    monkeypatch.setattr(
        django_ingestor,
        "_setup_project",
        lambda *args, **kwargs: registry,
    )

    django_ingestor.ingest_project(gateway, root)

    assert gateway.ops.resolve("energy.charger.filter") is None
    assert gateway("filter charger --site MTY") == {"site": "MTY"}
    assert gateway.ops.resolve("energy.charger.filter") is not None


def test_django_orm_sources_are_detected_without_explicit_kind(
    gateway,
    monkeypatch,
):
    Charger, manager = _orm_fixture()
    monkeypatch.setattr(
        django_ingestor,
        "_django_types",
        lambda: (_FakeModelBase, _FakeManagerBase),
    )

    assert django_ingestor.source_kind(Charger) == "model"
    assert django_ingestor.source_kind(Charger()) == "instance"
    assert django_ingestor.source_kind(manager) == "manager"


def test_model_operations_retain_app_qualified_canonical_paths(
    gateway,
    monkeypatch,
):
    Charger, _ = _orm_fixture()
    monkeypatch.setattr(
        django_ingestor,
        "_django_types",
        lambda: (_FakeModelBase, _FakeManagerBase),
    )

    gateway.ingest(Charger)

    assert gateway.ops.resolve("energy.charger.filter") is not None
    assert gateway.ops.resolve_pair("filter", "charger") is not None



def _management_fixture(monkeypatch):
    calls = []

    def get_commands():
        return {
            "collectstatic": "django.contrib.staticfiles",
            "migrate": "django.core",
            "rebuild_search": "search",
        }

    def call_command(name, *args, **options):
        calls.append((name, args, options))
        return {
            "command": name,
            "args": args,
            "options": options,
        }

    monkeypatch.setattr(
        django_ingestor,
        "_management_api",
        lambda: (get_commands, call_command),
    )
    return calls


def test_unnamed_django_mount_does_not_index_management_commands(
    gateway,
    tmp_path,
    monkeypatch,
):
    root, _ = _project(tmp_path)
    registry = SimpleNamespace(get_app_configs=lambda: ())
    monkeypatch.setattr(
        django_ingestor,
        "_setup_project",
        lambda *args, **kwargs: registry,
    )
    _management_fixture(monkeypatch)

    mount = django_ingestor.ingest_project(gateway, root)

    assert mount.management_enabled is False
    assert find_ingested(gateway, ("arthexis",)) is None
    assert django_ingestor.ingest_commands(gateway, mount) == []
    assert gateway.ops.resolve("migrate") is None


def test_named_mount_expands_management_commands_on_first_project_subject_use(
    gateway,
    tmp_path,
    monkeypatch,
):
    root, _ = _project(tmp_path)
    registry = SimpleNamespace(get_app_configs=lambda: ())
    monkeypatch.setattr(
        django_ingestor,
        "_setup_project",
        lambda *args, **kwargs: registry,
    )
    calls = _management_fixture(monkeypatch)

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
    tmp_path,
    monkeypatch,
):
    root, _ = _project(tmp_path)
    registry = SimpleNamespace(get_app_configs=lambda: ())
    monkeypatch.setattr(
        django_ingestor,
        "_setup_project",
        lambda *args, **kwargs: registry,
    )
    _management_fixture(monkeypatch)

    django_ingestor.ingest_project(gateway, root, name="arthexis")
    gateway("migrate arthexis")

    assert gateway.ops.resolve("migrate") is None
    assert gateway.ops.resolve_pair("migrate", "arthexis") is not None
    assert gateway.ops.resolve("arthexis.migrate") is not None


def test_management_command_passes_positionals_and_boolean_flags_to_django(
    gateway,
    tmp_path,
    monkeypatch,
):
    root, _ = _project(tmp_path)
    registry = SimpleNamespace(get_app_configs=lambda: ())
    monkeypatch.setattr(
        django_ingestor,
        "_setup_project",
        lambda *args, **kwargs: registry,
    )
    calls = _management_fixture(monkeypatch)

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
    tmp_path,
    monkeypatch,
):
    root, _ = _project(tmp_path)
    registry = SimpleNamespace(get_app_configs=lambda: ())
    monkeypatch.setattr(
        django_ingestor,
        "_setup_project",
        lambda *args, **kwargs: registry,
    )
    _management_fixture(monkeypatch)

    django_ingestor.ingest_project(gateway, root, name="arthexis")
    gateway("collectstatic arthexis")

    operation = gateway.ops.resolve("arthexis.collectstatic")
    assert operation.__gway_source_kind__ == "django-command"
    assert operation.__gway_subject__ == "arthexis"
    assert operation.__gway_metadata__["project"] == "arthexis"
    assert operation.__gway_metadata__["command"] == "collectstatic"


def test_management_command_expansion_is_idempotent(
    gateway,
    tmp_path,
    monkeypatch,
):
    root, _ = _project(tmp_path)
    registry = SimpleNamespace(get_app_configs=lambda: ())
    monkeypatch.setattr(
        django_ingestor,
        "_setup_project",
        lambda *args, **kwargs: registry,
    )

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
    tmp_path,
    monkeypatch,
):
    root, _ = _project(tmp_path)
    registry = SimpleNamespace(get_app_configs=lambda: ())
    monkeypatch.setattr(
        django_ingestor,
        "_setup_project",
        lambda *args, **kwargs: registry,
    )
    _management_fixture(monkeypatch)

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
