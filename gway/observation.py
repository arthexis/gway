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

    def observe(self, *command, mutate=False):
        """Execute one command read-only and return a structured observation envelope.

        Args:
            command: Command tokens to execute under the existing caller authority.
        """
        del mutate
        if not command:
            raise TypeError("observe requires a command")

        try:
            if self.gateway.authorization is not None:
                with self.gateway.external_authority():
                    result = self.gateway.execute(list(command), mutate=False)
            else:
                result = self.gateway.execute(list(command), mutate=False)
        except AuthorizationError as exception:
            return {
                "status": "unauthorized",
                "available": False,
                "result": None,
                "error": _error(exception),
            }
        except (OperationLookupError, LookupError, FileNotFoundError) as exception:
            return {
                "status": "unavailable",
                "available": False,
                "result": None,
                "error": _error(exception),
            }
        except MutationError as exception:
            return {
                "status": "blocked",
                "available": False,
                "result": None,
                "error": _error(exception),
            }
        except Exception as exception:
            return {
                "status": "error",
                "available": True,
                "result": None,
                "error": _error(exception),
            }

        return {
            "status": "ok",
            "available": True,
            "result": result,
            "error": None,
        }


def register(gateway):
    controller = Controller(gateway)
    gateway._observation_controller = controller
    gateway.wrap("observe", controller.observe)
    return controller
