import pytest

from gway.service import catalog_from_data


def test_service_catalog_normalizes_current_manifest_shape(tmp_path):
    catalog = catalog_from_data(
        {
            "project": {
                "name": "arthexis",
                "service_profile_file": ".locks/role.lck",
            },
            "services": {
                "web-local": {
                    "description": "Arthexis local web service",
                    "command": [
                        "{python}",
                        "manage.py",
                        "runserver",
                        "127.0.0.1:8888",
                        "--noreload",
                    ],
                    "working_directory": "{project}",
                    "writable_paths": [
                        "{project}/.locks",
                        "/opt/arthexis/var/log",
                    ],
                    "profiles": ["Terminal", "Watchtower"],
                    "restart": "on-failure",
                    "restart_sec": 5,
                    "environment": {
                        "PYTHONUNBUFFERED": "1",
                        "ARTHEXIS_MODE": "installed",
                    },
                }
            },
        },
        root=tmp_path,
    )

    assert catalog.project == "arthexis"
    assert catalog.root == tmp_path.resolve()
    assert catalog.profile_file == ".locks/role.lck"
    assert len(catalog.services) == 1

    service = catalog.services[0]
    assert service.identity == ("arthexis", "web-local")
    assert service.command == (
        "{python}",
        "manage.py",
        "runserver",
        "127.0.0.1:8888",
        "--noreload",
    )
    assert service.working_directory == "{project}"
    assert service.writable_paths == (
        "{project}/.locks",
        "/opt/arthexis/var/log",
    )
    assert service.profiles == ("Terminal", "Watchtower")
    assert service.restart == "on-failure"
    assert service.restart_sec == 5.0
    assert service.autostart is False
    assert dict(service.environment) == {
        "PYTHONUNBUFFERED": "1",
        "ARTHEXIS_MODE": "installed",
    }


def test_service_placeholders_remain_symbolic_during_manifest_parsing(tmp_path):
    catalog = catalog_from_data(
        {
            "project": {"name": "demo"},
            "services": {
                "worker": {
                    "command": ["{python}", "-m", "worker"],
                    "working_directory": "{project}",
                    "writable_paths": ["{project}/var"],
                }
            },
        },
        root=tmp_path,
    )

    service = catalog.get("worker")
    assert service.command[0] == "{python}"
    assert service.working_directory == "{project}"
    assert service.writable_paths == ("{project}/var",)


@pytest.mark.parametrize(
    ("services", "message"),
    [
        ({"worker": {}}, "command must not be empty"),
        (
            {"worker": {"command": "python worker.py"}},
            "command must be an array of strings",
        ),
        (
            {"worker": {"command": ["python"], "restart_sec": -1}},
            "restart_sec must be a non-negative number",
        ),
        (
            {"worker": {"command": ["python"], "environment": {"PORT": 8000}}},
            "environment.PORT must be a string",
        ),
    ],
)
def test_invalid_service_declarations_are_rejected(tmp_path, services, message):
    with pytest.raises(ValueError, match=message):
        catalog_from_data(
            {
                "project": {"name": "demo"},
                "services": services,
            },
            root=tmp_path,
        )
