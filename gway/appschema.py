"""Schema resolution and validation helpers for declarative application views."""

import importlib
import inspect
import sys


class SchemaReferenceError(LookupError):
    """Raised when a declared application schema cannot be resolved."""


class SchemaValidationError(ValueError):
    """Raised when a declared application schema rejects a value."""


def _is_schema(candidate):
    return callable(getattr(candidate, "model_validate", None))


def resolve_schema(gateway, handler, reference):
    """Resolve one schema reference without coupling Gway core to Pydantic."""
    if reference is None:
        return None
    if _is_schema(reference):
        return reference

    name = str(reference).strip()
    if not name:
        raise SchemaReferenceError("schema reference cannot be empty")

    try:
        candidate = gateway.context[name]
    except (KeyError, TypeError):
        candidate = None
    if _is_schema(candidate):
        return candidate

    candidate = gateway.ops.resolve(name)
    if _is_schema(candidate):
        return candidate

    original = inspect.unwrap(handler)
    module_name = getattr(original, "__module__", None)
    module = sys.modules.get(module_name) if module_name else None
    if module is not None:
        candidate = getattr(module, name, None)
        if _is_schema(candidate):
            return candidate

    if "." in name:
        import_name, _, attribute = name.rpartition(".")
        try:
            imported = importlib.import_module(import_name)
        except (ImportError, ValueError):
            imported = None
        if imported is not None:
            candidate = getattr(imported, attribute, None)
            if _is_schema(candidate):
                return candidate

    raise SchemaReferenceError(f"Unable to resolve schema: {name}")


def validate_schema(schema, value):
    """Validate one value with a Pydantic-compatible model class."""
    try:
        return schema.model_validate(value)
    except Exception as error:
        raise SchemaValidationError(str(error)) from error


def dump_schema_value(value):
    """Return a JSON-ready representation from a validated model when possible."""
    dump = getattr(value, "model_dump", None)
    if callable(dump):
        try:
            return dump(mode="json")
        except TypeError:
            return dump()
    return value
