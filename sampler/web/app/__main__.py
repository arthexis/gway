"""Lazy sampler registration for optional web application capability."""


def register(runtime):
    """Register the optional web/app semantic surface on demand."""
    from gway.application import register as register_application

    return register_application(runtime)
