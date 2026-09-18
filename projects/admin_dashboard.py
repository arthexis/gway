"""Admin dashboard data checks.

This module provides helpers to validate row level rules for admin-facing
models. The checks are designed to be CLI-friendly so they can be executed as
part of maintenance recipes or ad-hoc diagnostics.
"""

from __future__ import annotations

from typing import Any, Iterable

WATCHTOWER_TOKEN = "watchtower"


def check_user_row_rules(
    *,
    users: Iterable[object] | None = None,
    user_model: Any | None = None,
) -> dict[str, object]:
    """Validate admin dashboard row rules for the ``User`` model.

    Parameters
    ----------
    users:
        Optional iterable of user-like objects to validate. When omitted the
        function attempts to fetch all users from ``user_model`` (or the global
        Django ``User`` model if not provided).
    user_model:
        Django model providing an ``objects`` manager. Used when ``users`` is
        not supplied.

    Returns
    -------
    dict
        Summary of the validation outcome with an ``ok`` flag and collected
        errors (if any).
    """

    if users is not None and user_model is not None:
        # ``users`` take precedence – avoid ambiguous inputs.
        user_model = None

    resolved_users = list(users) if users is not None else _fetch_users(user_model)

    errors: list[dict[str, object]] = []
    superusers: list[object] = []

    for user in resolved_users:
        identifier = _describe_user(user)
        is_superuser = bool(getattr(user, "is_superuser", False))
        if is_superuser:
            superusers.append(user)

        is_staff = bool(getattr(user, "is_staff", False))
        username = getattr(user, "username", None) or getattr(user, "name", None)
        is_named_admin = isinstance(username, str) and username.lower() == "admin"
        is_admin = is_superuser or is_staff or is_named_admin

        if not is_admin:
            continue

        roles = _collect_role_tokens(user)
        watchtower_roles = {role for role in roles if _is_watchtower_role(role)}
        is_active = bool(getattr(user, "is_active", False))

        if watchtower_roles and is_active:
            errors.append(
                {
                    "code": "admin_watchtower_inactive",
                    "user": identifier,
                    "roles": sorted(watchtower_roles),
                    "message": "Admin users with watchtower roles must be inactive.",
                }
            )

    if superusers and not any(_has_email_configured(user) for user in superusers):
        errors.append(
            {
                "code": "superuser_email_required",
                "message": "At least one superuser must have an email address configured.",
            }
        )

    return {
        "ok": not errors,
        "errors": errors or None,
        "checked_users": len(resolved_users),
        "superusers": len(superusers),
    }


def _fetch_users(user_model: Any | None) -> list[object]:
    if user_model is None:
        from gway import gw

        user_model = gw.model.User

    objects = getattr(user_model, "objects", None)
    if objects is None or not hasattr(objects, "all"):
        raise ValueError("user_model must provide an 'objects' manager with an 'all' method")

    return list(objects.all())


def _describe_user(user: object) -> str:
    for attr in ("username", "name", "email", "id"):
        value = getattr(user, attr, None)
        if isinstance(value, str) and value.strip():
            return value
        if value:
            return str(value)
    return repr(user)


def _collect_role_tokens(user: object) -> set[str]:
    roles: set[str] = set()

    direct_roles = getattr(user, "roles", None)
    roles.update(_normalize_role_values(direct_roles))

    groups = getattr(user, "groups", None)
    if groups is not None:
        group_values = groups.all() if hasattr(groups, "all") else groups
        roles.update(_normalize_role_values(group_values))

    return {role for role in roles if role}


def _normalize_role_values(values: Any) -> set[str]:
    normalized: set[str] = set()

    if values is None:
        return normalized

    if isinstance(values, str):
        normalized.add(values.strip().lower())
        return normalized

    if isinstance(values, dict):
        values = values.values()

    try:
        iterator = iter(values)
    except TypeError:
        normalized.add(str(values).strip().lower())
        return normalized

    for value in iterator:
        if isinstance(value, str):
            normalized.add(value.strip().lower())
            continue
        name = getattr(value, "name", None)
        if isinstance(name, str) and name.strip():
            normalized.add(name.strip().lower())
            continue
        normalized.add(str(value).strip().lower())

    return normalized


def _is_watchtower_role(role: str) -> bool:
    simplified = role.replace("_", "").replace("-", "").replace(" ", "")
    return WATCHTOWER_TOKEN in simplified


def _has_email_configured(user: object) -> bool:
    email = getattr(user, "email", None)
    if email is None:
        return False
    email_text = str(email).strip()
    return bool(email_text)
