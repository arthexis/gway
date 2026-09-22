from gway.launchable import Launchable
from gway.service.model import Service


def test_service_can_wrap_operation_launchable(tmp_path):
    launchable = Launchable.operation("demo.worker", root=tmp_path)

    service = Service.from_launchable(
        "demo",
        "worker",
        tmp_path,
        launchable,
        restart="on-failure",
    )

    assert service.launchable is launchable
    assert service.restart == "on-failure"
