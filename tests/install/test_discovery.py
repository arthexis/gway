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



def test_installed_django_entrypoint_targets_real_app_not_project_alias(
    gateway,
    make_project,
    install_environment,
    tmp_path,
    monkeypatch,
):
    source = make_project("arthexis")
    (source / "manage.py").write_text(
        "import os\n"
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'demo.settings')\n",
        encoding="utf-8",
    )
    (source / "gway.toml").write_text(
        "[project]\n"
        "name = 'arthexis'\n"
        "aliases = ['ocpp']\n"
        "\n"
        "[ingest]\n"
        "django = '.'\n",
        encoding="utf-8",
    )
    gateway(f"install {source}")

    class ModelBase:
        pass

    class ManagerBase:
        pass

    class Charger(ModelBase):
        _meta = SimpleNamespace(
            app_label="ocpp",
            model_name="charger",
        )

    class ChargerManager(ManagerBase):
        model = Charger

        def filter(self, **criteria):
            return criteria

    Charger._default_manager = ChargerManager()
    app = SimpleNamespace(label="ocpp", get_models=lambda: [Charger])
    registry = SimpleNamespace(get_app_configs=lambda: (app,))

    monkeypatch.setattr(
        django_ingestor,
        "_setup_project",
        lambda root, settings=None: registry,
    )
    monkeypatch.setattr(
        django_ingestor,
        "_management_api",
        lambda: (
            lambda: {"migrate": "django.core"},
            lambda name, *args, **options: name,
        ),
    )
    monkeypatch.setattr(
        django_ingestor,
        "_django_types",
        lambda: (ModelBase, ManagerBase),
    )

    outside = tmp_path / "outside-entrypoint"
    outside.mkdir()
    monkeypatch.chdir(outside)
    fresh = Gateway()

    trigger = find_ingested(fresh, ("ocpp",))
    assert trigger is not None
    assert trigger.value.name == "arthexis"
    assert trigger.expanded is False

    assert fresh("ocpp charger filter --status online") == {
        "status": "online"
    }

    app_branch = find_ingested(fresh, ("ocpp",))
    assert app_branch is not None
    assert getattr(app_branch.value, "label", None) == "ocpp"
    assert fresh._installed_entrypoints["ocpp"] == "arthexis"

    with pytest.raises(LookupError):
        fresh("migrate ocpp")


def test_django_app_operations_allow_optional_project_prefix(
    gateway,
    make_project,
    install_environment,
    tmp_path,
    monkeypatch,
):
    source = make_project("arthexis")
    (source / "manage.py").write_text(
        "import os\n"
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'demo.settings')\n",
        encoding="utf-8",
    )
    (source / "gway.toml").write_text(
        "[project]\n"
        "name = 'arthexis'\n"
        "aliases = ['ocpp']\n"
        "\n"
        "[ingest]\n"
        "django = '.'\n",
        encoding="utf-8",
    )
    gateway(f"install {source}")

    class ModelBase:
        pass

    class ManagerBase:
        pass

    class Charger(ModelBase):
        _meta = SimpleNamespace(
            app_label="ocpp",
            model_name="charger",
        )

    class ChargerManager(ManagerBase):
        model = Charger

        def filter(self, **criteria):
            return criteria

    Charger._default_manager = ChargerManager()
    app = SimpleNamespace(label="ocpp", get_models=lambda: [Charger])
    registry = SimpleNamespace(get_app_configs=lambda: (app,))

    monkeypatch.setattr(
        django_ingestor,
        "_setup_project",
        lambda root, settings=None: registry,
    )
    monkeypatch.setattr(
        django_ingestor,
        "_management_api",
        lambda: (lambda: {}, lambda *args, **kwargs: None),
    )
    monkeypatch.setattr(
        django_ingestor,
        "_django_types",
        lambda: (ModelBase, ManagerBase),
    )

    outside = tmp_path / "outside-qualified"
    outside.mkdir()
    monkeypatch.chdir(outside)
    fresh = Gateway()

    assert fresh("arthexis ocpp charger filter --site MTY") == {
        "site": "MTY"
    }
    assert fresh("ocpp charger filter --site SLP") == {
        "site": "SLP"
    }

    canonical = fresh.ops.resolve("ocpp.charger.filter")
    qualified = fresh.ops.resolve("arthexis.ocpp.charger.filter")
    assert canonical is not None
    assert qualified is canonical



def test_uninstall_removes_project_from_future_gateway_bootstrap(
    gateway,
    make_project,
    install_environment,
    tmp_path,
    monkeypatch,
):
    source = make_project("wire")
    installed = gateway(f"install {source}")

    outside = tmp_path / "outside-uninstall"
    outside.mkdir()
    monkeypatch.chdir(outside)

    before = Gateway()
    assert before._installed["wire"] == installed
    assert find_ingested(before, ("wire",)) is not None

    removed = gateway("uninstall wire")
    assert removed == installed

    after = Gateway()
    assert "wire" not in after._installed
    assert find_ingested(after, ("wire",)) is None


def test_uninstall_removes_lazy_project_entrypoints_from_future_bootstrap(
    gateway,
    make_project,
    install_environment,
    tmp_path,
    monkeypatch,
):
    source = make_project("arthexis")
    (source / "gway.toml").write_text(
        "[project]\n"
        "name = 'arthexis'\n"
        "aliases = ['ocpp', 'energy']\n",
        encoding="utf-8",
    )
    gateway(f"install {source}")

    outside = tmp_path / "outside-entrypoint-uninstall"
    outside.mkdir()
    monkeypatch.chdir(outside)

    before = Gateway()
    assert before._installed_entrypoints == {
        "ocpp": "arthexis",
        "energy": "arthexis",
    }
    assert find_ingested(before, ("ocpp",)) is not None
    assert find_ingested(before, ("energy",)) is not None

    gateway("uninstall arthexis")

    after = Gateway()
    assert after._installed == {}
    assert after._installed_entrypoints == {}
    assert find_ingested(after, ("ocpp",)) is None
    assert find_ingested(after, ("energy",)) is None


def test_upgrade_refreshes_discovered_entrypoints_for_new_gateway(
    gateway,
    make_project,
    install_environment,
    tmp_path,
    monkeypatch,
):
    source = make_project("arthexis")
    manifest = source / "gway.toml"
    manifest.write_text(
        "[project]\n"
        "name = 'arthexis'\n"
        "aliases = ['ocpp']\n",
        encoding="utf-8",
    )
    first = gateway(f"install {source}")

    outside = tmp_path / "outside-upgrade"
    outside.mkdir()
    monkeypatch.chdir(outside)

    initial = Gateway()
    assert initial._installed_entrypoints == {"ocpp": "arthexis"}
    assert find_ingested(initial, ("ocpp",)) is not None
    assert find_ingested(initial, ("energy",)) is None

    manifest.write_text(
        "[project]\n"
        "name = 'arthexis'\n"
        "aliases = ['energy']\n",
        encoding="utf-8",
    )
    second = gateway(f"install {source}")

    assert second.fingerprint != first.fingerprint

    refreshed = Gateway()
    assert refreshed._installed_entrypoints == {"energy": "arthexis"}
    assert find_ingested(refreshed, ("ocpp",)) is None
    assert find_ingested(refreshed, ("energy",)) is not None


def test_system_installation_remains_discoverable_after_user_uninstall(
    gateway,
    make_project,
    install_environment,
    tmp_path,
    monkeypatch,
):
    system_source = make_project("shared")
    system = gateway(f"install {system_source} --system")

    user_source = make_project("shared")
    user = gateway(f"install {user_source}")

    outside = tmp_path / "outside-scope-fallback"
    outside.mkdir()
    monkeypatch.chdir(outside)

    before = Gateway()
    assert before._installed["shared"] == user

    gateway("uninstall shared")

    after = Gateway()
    assert after._installed["shared"] == system
    assert find_ingested(after, ("shared",)).value == system
