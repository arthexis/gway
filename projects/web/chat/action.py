"""Alias for ChatGPT Actions.

This module exposes the same functionality as ``web.chat.actions``
under the shorter project name ``web.chat.action`` so the API endpoint
is registered as ``/api/web/chat/action``.
"""

from gway import gw


def _actions():
    """Return the real actions module lazily to avoid import loops."""
    return gw.web.chat.actions


def api_post_action(*args, **kwargs):
    return _actions().api_post_action(*args, **kwargs)


def api_get_manifest(*args, **kwargs):
    return _actions().api_get_manifest(*args, **kwargs)


def api_get_openapi_json(*args, **kwargs):
    return _actions().api_get_openapi_json(*args, **kwargs)


def api_post_trust(*args, **kwargs):
    return _actions().api_post_trust(*args, **kwargs)


def view_trust_status(*args, **kwargs):
    return _actions().view_trust_status(*args, **kwargs)


def view_audit_chatlog(*args, **kwargs):
    return _actions().view_audit_chatlog(*args, **kwargs)
