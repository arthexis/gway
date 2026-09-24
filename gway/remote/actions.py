"""GPT Actions compatibility surface for remote Gway execution."""

import json
import threading
from urllib.parse import urlsplit

from ..authorization import AuthorizationError
from ..mutation import MutationError
from ..security.authentication import BearerAuthenticationError


MAX_ACTION_COMMAND_BYTES = 16 * 1024


class ActionsApplication:
    """Serve the temporary GPT Actions HTTP compatibility endpoints."""

    prefix = "/actions"

    def __init__(self, metadata, *, runtime=None):
        self.metadata = metadata
        self.runtime = runtime
        self._execution_lock = threading.RLock()

    def openapi_document(self):
        """Return the stable GPT Actions transport contract."""

        command_schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["command"],
            "properties": {
                "command": {
                    "type": "string",
                    "minLength": 1,
                    "description": "A complete Gway command string.",
                }
            },
        }
        result_schema = {
            "type": "object",
            "required": ["result"],
            "properties": {
                "result": {},
            },
            "additionalProperties": False,
        }
        error_schema = {
            "type": "object",
            "required": ["error"],
            "properties": {
                "error": {"type": "string"},
                "message": {"type": "string"},
            },
            "additionalProperties": True,
        }

        def operation(operation_id, summary, description):
            return {
                "operationId": operation_id,
                "summary": summary,
                "description": description,
                "security": [{"oauth2": []}],
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": command_schema,
                        }
                    },
                },
                "responses": {
                    "200": {
                        "description": "Gway command result.",
                        "content": {
                            "application/json": {
                                "schema": result_schema,
                            }
                        },
                    },
                    "400": {
                        "description": "Invalid request or Gway command.",
                        "content": {
                            "application/json": {
                                "schema": error_schema,
                            }
                        },
                    },
                    "401": {
                        "description": "Missing or invalid bearer token.",
                        "content": {
                            "application/json": {
                                "schema": error_schema,
                            }
                        },
                    },
                    "403": {
                        "description": "The authenticated Gway scope does not authorize the command.",
                        "content": {
                            "application/json": {
                                "schema": error_schema,
                            }
                        },
                    },
                    "409": {
                        "description": "The requested command violates the read-only mutation ceiling.",
                        "content": {
                            "application/json": {
                                "schema": error_schema,
                            }
                        },
                    },
                    "503": {
                        "description": "The remote Actions runtime is unavailable.",
                        "content": {
                            "application/json": {
                                "schema": error_schema,
                            }
                        },
                    },
                },
            }

        return {
            "openapi": "3.1.0",
            "info": {
                "title": "Gway Remote Actions",
                "version": "1.0.0",
                "description": (
                    "Stable GPT Actions transport for executing Gway command strings. "
                    "Gway operations are discovered through Gway itself, not enumerated "
                    "in this OpenAPI document."
                ),
            },
            "servers": [{"url": self.metadata.issuer}],
            "paths": {
                "/actions/query": {
                    "post": operation(
                        "queryGway",
                        "Execute a read-only Gway command",
                        (
                            "Execute one Gway command under the authenticated user's "
                            "current named scopes with a hard non-mutating ceiling. "
                            "Use Gway help when command syntax needs discovery."
                        ),
                    )
                },
                "/actions/execute": {
                    "post": operation(
                        "executeGway",
                        "Execute an authorized Gway command",
                        (
                            "Execute one Gway command under the authenticated user's "
                            "current named scopes. Mutation is possible only when the "
                            "specific canonical Gway operation is authorized."
                        ),
                    )
                },
            },
            "components": {
                "securitySchemes": {
                    "oauth2": {
                        "type": "oauth2",
                        "flows": {
                            "authorizationCode": {
                                "authorizationUrl": self.metadata.authorization_endpoint,
                                "tokenUrl": self.metadata.token_endpoint,
                                "scopes": {},
                            }
                        },
                    }
                }
            },
        }

    @staticmethod
    def _bearer(headers):
        authorization = (headers or {}).get("authorization", "")
        scheme, separator, credential = authorization.partition(" ")
        if not separator or scheme.casefold() != "bearer" or not credential.strip():
            raise BearerAuthenticationError()
        return credential.strip()

    @staticmethod
    def _json_body(body):
        try:
            if isinstance(body, bytes):
                body = body.decode("utf-8")
            payload = json.loads(str(body))
        except (TypeError, ValueError, UnicodeDecodeError):
            raise ValueError("Request body must be valid JSON") from None
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object")
        return payload

    @classmethod
    def _json_safe(cls, value):
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, dict):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set, frozenset)):
            return [cls._json_safe(item) for item in value]
        if hasattr(value, "__dict__"):
            return {
                str(key): cls._json_safe(item)
                for key, item in vars(value).items()
                if not str(key).startswith("_")
            }
        return str(value)

    @staticmethod
    def _response_headers():
        return {
            "content-type": "application/json",
            "cache-control": "no-store",
            "pragma": "no-cache",
        }

    def _execute(self, method, headers, body, *, mutate):
        response_headers = self._response_headers()
        if method != "POST":
            return 405, {**response_headers, "allow": "POST"}, {
                "error": "method_not_allowed"
            }
        if self.runtime is None:
            return 503, response_headers, {"error": "actions_unavailable"}

        try:
            payload = self._json_body(body)
        except ValueError as error:
            return 400, response_headers, {
                "error": "invalid_request",
                "message": str(error),
            }

        command = payload.get("command")
        if not isinstance(command, str) or not command.strip():
            return 400, response_headers, {
                "error": "invalid_request",
                "message": "JSON field 'command' is required",
            }
        if len(command.encode("utf-8")) > MAX_ACTION_COMMAND_BYTES:
            return 400, response_headers, {
                "error": "query_too_large",
                "message": "Command exceeds the maximum size",
            }

        try:
            bearer = self._bearer(headers)
            with self._execution_lock:
                kwargs = {
                    "resource": self.metadata.resource,
                }
                if mutate is False:
                    kwargs["mutate"] = False
                result = self.runtime.execute_authenticated(
                    bearer,
                    command,
                    **kwargs,
                )
        except BearerAuthenticationError:
            return 401, {
                **response_headers,
                "www-authenticate": "Bearer",
            }, {"error": "invalid_bearer"}
        except AuthorizationError as error:
            return 403, response_headers, {
                "error": "not_authorized",
                "message": str(error),
            }
        except MutationError as error:
            return 409, response_headers, {
                "error": "mutation_not_allowed",
                "message": str(error),
            }
        except (LookupError, TypeError, ValueError) as error:
            return 400, response_headers, {
                "error": "invalid_command",
                "message": str(error),
            }

        return 200, response_headers, {"result": self._json_safe(result)}

    def response(self, method, path, *, headers=None, body=b""):
        method = str(method).upper()
        route = urlsplit(str(path)).path
        headers = {str(k).casefold(): str(v) for k, v in (headers or {}).items()}

        if route == "/actions/openapi.json":
            if method != "GET":
                return 405, {"allow": "GET"}, {"error": "method_not_allowed"}
            return 200, {"content-type": "application/json"}, self.openapi_document()

        if route == "/actions/query":
            return self._execute(method, headers, body, mutate=False)
        if route == "/actions/execute":
            return self._execute(method, headers, body, mutate=None)
        return 404, {}, {"error": "not_found"}
