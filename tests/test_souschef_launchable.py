from gway.launchable import Launchable
from gway.service.model import Service
from gway.souschef.service import definition


def test_service_requires_launchable(tmp_path):
    try:
        Service(project="demo", name="worker", root=tmp_path)
    except TypeError:
        pass
    else:
        raise AssertionError("Service should require a launchable")


def test_sous_chef_uses_generic_launchable():
    service = definition()

    assert isinstance(service.launchable, Launchable)
    assert service.launchable.kind == "command"
    assert service.launchable.command == (
        "{python}",
        "-m",
        "gway.souschef.daemon",
    )
    assert service.name == "sous-chef"
