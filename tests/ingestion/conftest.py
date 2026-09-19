from types import SimpleNamespace

import pytest

import gway.ingestion.django as django_ingestor


@pytest.fixture
def make_ping_node():
    class PingNode:
        def __init__(self, result="pong"):
            self.result = result

        def ping(self):
            return self.result

    return PingNode


@pytest.fixture
def django_project(tmp_path):
    """Create a conventional Django project root with manage.py."""

    def make(name="project", settings="demo.settings"):
        root = tmp_path / name
        root.mkdir()
        manage = root / "manage.py"
        manage.write_text(
            "import os\n"
            f"os.environ.setdefault('DJANGO_SETTINGS_MODULE', {settings!r})\n",
            encoding="utf-8",
        )
        return root, manage

    return make


@pytest.fixture
def django_setup(monkeypatch):
    """Stub Django setup with a registry containing the supplied apps."""

    def install(*apps):
        registry = SimpleNamespace(get_app_configs=lambda: tuple(apps))
        monkeypatch.setattr(
            django_ingestor,
            "_setup_project",
            lambda *args, **kwargs: registry,
        )
        return registry

    return install


@pytest.fixture
def django_management(monkeypatch):
    """Install a fake Django management registry and capture executions."""

    def install(commands=None):
        calls = []
        command_map = commands or {
            "collectstatic": "django.contrib.staticfiles",
            "migrate": "django.core",
            "rebuild_search": "search",
        }

        def get_commands():
            return dict(command_map)

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

    return install


@pytest.fixture
def django_orm(monkeypatch):
    """Provide fake Django model/manager types and one Charger surface."""

    class ModelBase:
        pass

    class ManagerBase:
        pass

    class Charger(ModelBase):
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

    class ChargerManager(ManagerBase):
        model = Charger

        def all(self):
            return ["all"]

        def filter(self, **criteria):
            return criteria

        def create(self, **values):
            return Charger(**values)

    manager = ChargerManager()
    Charger._default_manager = manager

    monkeypatch.setattr(
        django_ingestor,
        "_django_types",
        lambda: (ModelBase, ManagerBase),
    )

    return Charger, manager
