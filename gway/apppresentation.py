"""Request policy and sigil-aware template helpers for AppSpec views."""

from collections.abc import Mapping
from pathlib import Path


class PolicyContractError(RuntimeError):
    """Raised when a named view policy returns an unsupported result."""


class TemplateRenderError(RuntimeError):
    """Raised when a declared view template cannot be rendered."""


def evaluate_policy(gateway, policy):
    """Evaluate one named request policy inside the active request scope."""
    if policy in (None, "public"):
        return None

    result = gateway(policy)
    if result is None or result is True:
        return None
    if result is False:
        return 403, {}, {"error": "forbidden"}
    if (
        isinstance(result, tuple)
        and len(result) == 3
        and isinstance(result[0], int)
    ):
        return result
    raise PolicyContractError(
        f"Policy {policy!r} must return True, False, None, or "
        "(status, headers, payload)"
    )


def _template_context(mapping, method, payload):
    context = {
        "view": mapping.name or (
            mapping.handler.rsplit(".", 1)[-1]
            if mapping.handler
            else None
        ),
        "route": mapping.route,
        "method": method,
    }
    if isinstance(payload, Mapping):
        context.update(dict(payload))
    else:
        context["result"] = payload
    return context


def render_template(gateway, app, mapping, method, payload):
    """Render one declared template with request-local sigil context."""
    expression = mapping.template
    if not expression:
        return payload

    context = _template_context(mapping, method, payload)
    try:
        context["request"] = gateway.context["request"]
    except (KeyError, TypeError):
        pass
    with gateway.request_scope(context=context):
        resolved_name = gateway.resolve(expression)

    path = Path(str(resolved_name)).expanduser()
    if not path.is_absolute():
        if not app.templates:
            raise TemplateRenderError(
                "relative view template requires an application template base"
            )
        path = Path(app.templates) / path

    try:
        content = path.read_text(encoding="utf-8")
    except OSError as error:
        raise TemplateRenderError(str(error)) from error

    with gateway.request_scope(context=context):
        rendered = gateway.resolve(content)
    return rendered if isinstance(rendered, str) else str(rendered)
