"""Portable Gway-managed service installation backend."""

from ..service.runtime import ProcessBackend
from .systemd import UnitRecord, UnitState


BACKEND = "process"


def install_units(
    project,
    services,
    *,
    state_root,
    system=False,
    name=None,
    root=None,
):
    """Persist process-backed service ownership without starting services."""
    services = list(services)
    if name is not None and len(services) != 1:
        raise ValueError("--name requires exactly one selected service")

    state = UnitState(state_root)
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
            name
            if name is not None
            else previous_record.unit if previous_record is not None else service.name
        )
        records.append(
            UnitRecord(
                project=project,
                service=service.name,
                unit=runtime_name,
                system=system,
                backend=BACKEND,
            )
        )

    state.put(project, [*foreign, *records])
    return records


def uninstall_units(project, *, state_root, root=None, records=None):
    """Stop and remove process-backed service ownership records."""
    state = UnitState(state_root)
    all_records = state.get(project)
    records = (
        [record for record in all_records if record.backend == BACKEND]
        if records is None
        else list(records)
    )
    if not records:
        return []

    # Process-backed services use ProcessBackend durable state below the same
    # Gway installation root. Service definitions are not required here:
    # package uninstall routes stop through the service controller before the
    # managed project tree is removed.
    removed = {(record.backend, record.service, record.unit) for record in records}
    remaining = [
        record
        for record in all_records
        if (record.backend, record.service, record.unit) not in removed
    ]
    state.put(project, remaining)
    return records


def runtime(*, installations=None, state_root=None):
    """Return the portable runtime backend for installed process services."""
    return ProcessBackend(
        installations=installations,
        state_root=state_root,
    )
