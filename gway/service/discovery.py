"""Discovery of service declarations from managed project manifests."""

from pathlib import Path

from .manifest import load


def declares_services(manifest):
    """Return whether one manifest declares any service table."""
    for raw in Path(manifest).read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line == "[services]" or line.startswith("[services."):
            return True
    return False


def discover(runtime, installations):
    """Index service catalogs from selected managed installations."""
    catalogs = {}
    services = {}

    for installation in installations:
        manifest = installation.install_path / "gway.toml"
        if not declares_services(manifest):
            continue

        catalog = load(manifest)
        if catalog.project != installation.name:
            raise RuntimeError(
                "Installed project service manifest identity does not match "
                f"installation state: {catalog.project!r} != {installation.name!r}"
            )

        catalogs[catalog.project] = catalog
        for service in catalog.services:
            services[service.identity] = service

    runtime._service_catalogs = catalogs
    runtime._services = services
    return services
