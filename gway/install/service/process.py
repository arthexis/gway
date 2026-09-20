"""Portable Gway-managed service installation backend."""

from ...service.runtime import ProcessBackend
from .state import ServiceInstallRecord, ServiceInstallState


BACKEND = "process"


def install_units(
    project,
    services,
    *,
    state_root,
    system=False,
    root=None,
):
    """Persist process-backed service ownership without starting services."""
    services = list(services)

    state = ServiceInstallState(state_root)
    previous_all = state.get(project)
    previous = {
        record.service: record
        for record in previous_all
        if record.backend == BACKEND
    }
    foreign = [
        record
        for record in previous_all
        if record.backend != BACKEND
    ]

    records = []
    for service in services:
        previous_record = previous.get(service.name)
        runtime_name = (
            previous_record.backend_id
            if previous_record is not None
            else service.name
        )
        records.append(
            ServiceInstallRecord(
                project=project,
                service=service.name,
                backend_id=runtime_name,
                system=system,
                backend=BACKEND,
                restart=service.restart,
                attempts=service.attempts,
                restart_sec=service.restart_sec,
                command=tuple(service.launchable.command),
            )
        )

    state.put(project, [*foreign, *records])
    return records


def uninstall_units(
    project,
    *,
    state_root,
    root=None,
    records=None,
    services=(),
    installations=None,
    process_state_root=None,
):
    """Stop and remove process-backed service ownership records."""
    state = ServiceInstallState(state_root)
    all_records = state.get(project)
    records = (
        [record for record in all_records if record.backend == BACKEND]
        if records is None
        else list(records)
    )
    if not records:
        return []

    definitions = {service.name: service for service in services}
    backend = ProcessBackend(
        installations=installations,
        state_root=process_state_root,
    )
    for record in records:
        service = definitions.get(record.service)
        if service is not None:
            backend.stop(service)

    removed = {(record.backend, record.service, record.backend_id) for record in records}
    remaining = [
        record
        for record in all_records
        if (record.backend, record.service, record.backend_id) not in removed
    ]
    state.put(project, remaining)
    return records


def runtime(*, record=None, installations=None, state_root=None):
    """Return the portable runtime backend for installed process services."""
    return ProcessBackend(
        installations=installations,
        state_root=state_root,
    )
