from types import SimpleNamespace

import pytest

from gway import Gateway
from gway.ingestion.base import find_ingested
from gway.install import Installation, InstallState
import gway.ingestion.django as django_ingestor


@pytest.fixture(autouse=True)
def isolate_system_installations(tmp_path, monkeypatch):
    monkeypatch.setenv("GWAY_SYSTEM_DATA_DIR", str(tmp_path / "system-data"))
    monkeypatch.setenv("GWAY_SYSTEM_BIN_DIR", str(tmp_path / "system-bin"))


def test_fresh_gateway_discovers_managed_user_installation(
    gateway,
    make_project,
    install_environment,
    tmp_path,
    monkeypatch,
):
    source = make_project("wire")
    installed = gateway(f"install {source}")

    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)

    fresh = Gateway()

    assert fresh._installed == {"wire": installed}
    record = find_ingested(fresh, ("wire",))
    assert record is not None
    assert record.value == installed
    assert record.expanded is False
    assert callable(record.expander)
    assert fresh.ops.resolve("wire") is None


def test_installed_project_discovery_does_not_eagerly_ingest_django(
    gateway,
    make_project,
    install_environment,
    tmp_path,
    monkeypatch,
):
    source = make_project("backend")
    (source / "manage.py").write_text("# django entry\n", encoding="utf-8")
    (source / "gway.toml").write_text(
        "[project]\n"
        "name = 'backend'\n"
        "\n"
        "[ingest]\n"
        "django = '.'\n",
        encoding="utf-8",
    )
    gateway(f"install {source}")

    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)

    import gway.ingestion.django as django_ingestor

    calls = []

    def unexpected_ingest(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("installed project was ingested eagerly")

    monkeypatch.setattr(django_ingestor, "ingest_project", unexpected_ingest)
    fresh = Gateway()

    assert "backend" in fresh._installed
    assert calls == []
    assert fresh.ops.resolve("backend") is None


def test_discovery_skips_stale_or_unsafe_installation_records(
    install_environment,
    tmp_path,
    monkeypatch,
):
    state = InstallState(install_environment.data / "state.sqlite")
    expected = install_environment.data / "projects" / "missing"
    outside = tmp_path / "outside-project"
    outside.mkdir()
    (outside / "gway.toml").write_text(
        "[project]\nname = 'outside'\n",
        encoding="utf-8",
    )

    state.put(
        Installation(
            name="missing",
            source="test",
            install_path=expected,
        )
    )
    state.put(
        Installation(
            name="outside",
            source="test",
            install_path=outside,
        )
    )

    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    fresh = Gateway()

    assert fresh._installed == {}
    assert find_ingested(fresh, ("missing",)) is None
    assert find_ingested(fresh, ("outside",)) is None


def test_user_installation_wins_unqualified_name_over_system_installation(
    gateway,
    make_project,
    install_environment,
    tmp_path,
    monkeypatch,
):
    system_data = tmp_path / "system-data"
    system_bin = tmp_path / "system-bin"
    monkeypatch.setenv("GWAY_SYSTEM_DATA_DIR", str(system_data))
    monkeypatch.setenv("GWAY_SYSTEM_BIN_DIR", str(system_bin))

    user_source = make_project("shared")
    user = gateway(f"install {user_source}")

    system_source = make_project("shared")
    (system_source / "module.py").write_text("VALUE = 2\n", encoding="utf-8")
    system = gateway(f"install {system_source} --system")

    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.chdir(outside)
    fresh = Gateway()

    assert fresh._installed["shared"] == user
    assert fresh._installed["shared"] != system
    record = find_ingested(fresh, ("shared",))
    assert record.value == user



def test_installed_django_project_expands_lazily_for_commands_and_models(
    gateway,
    make_project,
    install_environment,
    tmp_path,
    monkeypatch,
):
    source = make_project("backend")
    (source / "manage.py").write_text(
        "import os\n"
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'demo.settings')\n",
        encoding="utf-8",
    )
    (source / "gway.toml").write_text(
        "[project]\n"
        "name = 'backend'\n"
        "\n"
        "[ingest]\n"
        "django = '.'\n",
        encoding="utf-8",
    )
    installed = gateway(f"install {source}")

    class ModelBase:
        pass

    class ManagerBase:
        pass

    class Charger(ModelBase):
        _meta = SimpleNamespace(
            app_label="energy",
            model_name="charger",
        )

    class ChargerManager(ManagerBase):
        model = Charger

        def filter(self, **criteria):
            return criteria

    Charger._default_manager = ChargerManager()
    app = SimpleNamespace(
        label="energy",
        get_models=lambda: [Charger],
    )
    registry = SimpleNamespace(get_app_configs=lambda: (app,))
    setup_calls = []

    def fake_setup(root, *, settings=None):
        setup_calls.append((root, settings))
        return registry

    management_calls = []

    def get_commands():
        return {"migrate": "django.core"}

    def call_command(name, *args, **options):
        management_calls.append((name, args, options))
        return {
            "command": name,
            "args": args,
            "options": options,
        }

    monkeypatch.setattr(django_ingestor, "_setup_project", fake_setup)
    monkeypatch.setattr(
        django_ingestor,
        "_management_api",
        lambda: (get_commands, call_command),
    )
    monkeypatch.setattr(
        django_ingestor,
        "_django_types",
        lambda: (ModelBase, ManagerBase),
    )

    outside = tmp_path / "outside-django"
    outside.mkdir()
    monkeypatch.chdir(outside)
    fresh = Gateway()

    branch = find_ingested(fresh, ("backend",))
    assert branch.value == installed
    assert branch.expanded is False
    assert setup_calls == []

    result = fresh("migrate backend --database default")

    assert result == {
        "command": "migrate",
        "args": (),
        "options": {"database": "default"},
    }
    assert management_calls == [
        ("migrate", (), {"database": "default"}),
    ]
    assert branch.expanded is True
    assert setup_calls == [
        (installed.install_path.resolve(), "demo.settings"),
    ]

    assert fresh("filter charger --site MTY") == {"site": "MTY"}
    assert fresh.ops.resolve("energy.charger.filter") is not None


def test_installed_project_manifest_expansion_is_idempotent(
    gateway,
    make_project,
    install_environment,
    tmp_path,
    monkeypatch,
):
    source = make_project("backend")
    (source / "manage.py").write_text(
        "import os\n"
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'demo.settings')\n",
        encoding="utf-8",
    )
    (source / "gway.toml").write_text(
        "[project]\n"
        "name = 'backend'\n"
        "\n"
        "[ingest]\n"
        "django = '.'\n",
        encoding="utf-8",
    )
    gateway(f"install {source}")

    registry = SimpleNamespace(get_app_configs=lambda: ())
    setup_calls = []
    monkeypatch.setattr(
        django_ingestor,
        "_setup_project",
        lambda root, settings=None: (
            setup_calls.append((root, settings)) or registry
        ),
    )
    monkeypatch.setattr(
        django_ingestor,
        "_management_api",
        lambda: (
            lambda: {"migrate": "django.core"},
            lambda name, *args, **options: name,
        ),
    )

    outside = tmp_path / "outside-idempotent"
    outside.mkdir()
    monkeypatch.chdir(outside)
    fresh = Gateway()

    assert fresh("migrate backend") == "migrate"
    assert fresh("migrate backend") == "migrate"
    assert len(setup_calls) == 1
