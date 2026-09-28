"""Structured observation boundaries for read-only composition."""

from .authorization import AuthorizationError
from .dispatch import OperationLookupError
from .mutation import MutationError


def _error(exception):
    return {
        "type": type(exception).__name__,
        "message": str(exception),
    }


class Controller:
    """Execute one command observationally and capture bounded failure metadata."""

    def __init__(self, gateway):
        self.gateway = gateway

    def observe(self, *command, section=None, mutate=False):
        """Execute one command read-only and return a structured observation envelope.

        Args:
            command: Command tokens to execute under the existing caller authority.
            section: Optional context key used to publish the observation for composition.
        """
        del mutate
        if not command:
            raise TypeError("observe requires a command")

        target = command[0] if len(command) == 1 and isinstance(command[0], str) else list(command)
        try:
            if self.gateway.authorization is not None:
                with self.gateway.external_authority():
                    result = self.gateway.execute(target, mutate=False)
            else:
                result = self.gateway.execute(target, mutate=False)
        except AuthorizationError as exception:
            envelope = {
                "status": "unauthorized",
                "available": False,
                "result": None,
                "error": _error(exception),
            }
            if section is not None:
                return {str(section): envelope}
            return envelope
        except (OperationLookupError, LookupError, FileNotFoundError) as exception:
            envelope = {
                "status": "unavailable",
                "available": False,
                "result": None,
                "error": _error(exception),
            }
            if section is not None:
                return {str(section): envelope}
            return envelope
        except MutationError as exception:
            envelope = {
                "status": "blocked",
                "available": False,
                "result": None,
                "error": _error(exception),
            }
            if section is not None:
                return {str(section): envelope}
            return envelope
        except Exception as exception:
            envelope = {
                "status": "error",
                "available": True,
                "result": None,
                "error": _error(exception),
            }
            if section is not None:
                return {str(section): envelope}
            return envelope

        envelope = {
            "status": "ok",
            "available": True,
            "result": result,
            "error": None,
        }
        if section is not None:
            return {str(section): envelope}
        return envelope

    def status(self, *section, mutate=False):
        """Summarize named observation envelopes already present in semantic context."""
        del mutate
        names = tuple(str(name) for name in section)
        if not names:
            raise TypeError("observation status requires at least one section")

        states = {}
        degraded = []
        counts = {}
        for name in names:
            envelope = self.gateway.context.get(name)
            status = (
                envelope.get("status")
                if isinstance(envelope, dict)
                else "unavailable"
            )
            states[name] = status
            counts[status] = counts.get(status, 0) + 1
            if status in {"error", "blocked", "unauthorized"}:
                degraded.append(name)

        return {
            "health": {
                "status": "degraded" if degraded else "ok",
                "sections": states,
                "counts": counts,
                "degraded": degraded,
            }
        }


def register(gateway):
    controller = Controller(gateway)
    gateway._observation_controller = controller
    gateway.wrap("observe", controller.observe)
    gateway.wrap(
        "observation.status",
        controller.status,
        op="status",
        sub="observation",
    )
    return controller
