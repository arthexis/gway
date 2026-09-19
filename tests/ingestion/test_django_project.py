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


def test_manage_path_is_recognized_as_django_project(django_project):
    root, manage = django_project()

    assert django_ingestor.is_project_path(manage)
    assert django_ingestor.is_project_path(root)


def test_project_mount_discovers_settings_from_manage_and_indexes_apps_models(
    gateway,
    django_project,
    monkeypatch,
):
    root, _ = django_project()
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
    django_project,
    django_setup,
):
    root, _ = django_project()
    energy_charger = _model("charger")
    legacy_charger = _model("charger")
    django_setup(
        _app("energy", [energy_charger]),
        _app("legacy", [legacy_charger]),
    )

    django_ingestor.ingest_project(gateway, root)

    assert find_ingested(gateway, ("energy", "charger")).value is energy_charger
    assert find_ingested(gateway, ("legacy", "charger")).value is legacy_charger
    assert find_ingested(gateway, ("charger",)) is None


def test_named_project_mount_authorizes_management_command_indexing(
    gateway,
    django_project,
    django_setup,
    django_management,
):
    root, _ = django_project()
    django_setup()
    django_management()

    mount = django_ingestor.ingest_project(gateway, root, name="arthexis")

    assert mount.name == "arthexis"
    assert mount.management_enabled is True
    assert gateway.ops.resolve("migrate") is None


def test_reingesting_unnamed_project_can_add_project_name(
    gateway,
    django_project,
    django_setup,
    django_management,
):
    root, _ = django_project()
    django_setup()
    django_management()

    first = django_ingestor.ingest_project(gateway, root)
    second = django_ingestor.ingest_project(gateway, root, name="arthexis")

    assert second is first
    assert first.name == "arthexis"
    assert first.management_enabled is True


def test_reingesting_named_project_with_different_name_is_rejected(
    gateway,
    django_project,
    django_setup,
    django_management,
):
    root, _ = django_project()
    django_setup()
    django_management()

    django_ingestor.ingest_project(gateway, root, name="first")

    with pytest.raises(ValueError, match="already mounted"):
        django_ingestor.ingest_project(gateway, root, name="second")


def test_settings_module_source_can_mount_django_without_manage_py(
    gateway,
    tmp_path,
    monkeypatch,
    django_management,
):
    monkeypatch.chdir(tmp_path)
    registry = SimpleNamespace(get_app_configs=lambda: ())
    seen = {}

    def fake_setup(root, *, settings=None):
        seen["root"] = Path(root)
        seen["settings"] = settings
        return registry

    monkeypatch.setattr(django_ingestor, "_setup_project", fake_setup)
    django_management()

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
