# file: projects/web/chat/actions.py
"""ChatGPT Actions utilities with simple passphrase authentication."""

import time
import random

from gway import gw

# In-memory trust store: {session_id: {"trust": ..., "ts": ..., "count": ...}}
_TRUSTS = {}
_TRUST_TTL = 900  # 15 minutes
_TRUST_MAX_ACTIONS = 20

_ADJECTIVES = [
    "brave", "bright", "calm", "clever", "daring", "eager", "fuzzy", "gentle",
    "happy", "jolly", "kind", "lucky", "merry", "quick", "quiet", "silly",
]
_NOUNS = [
    "fox", "lion", "panda", "eagle", "river", "mountain", "forest", "ocean",
    "star", "cloud", "comet", "breeze", "flame", "shadow", "valley", "stone",
]


def _random_passphrase() -> str:
    """Return a short random phrase easy to share verbally."""
    return f"{random.choice(_ADJECTIVES)}-{random.choice(_NOUNS)}-{random.randint(100, 999)}"


def _get_session_id(request):
    ip = request.remote_addr or "unknown"
    ua = request.headers.get("User-Agent", "")
    cookie = request.cookies.get("chat_session", "")
    return f"{ip}:{ua}:{cookie}"


def api_post_action(*, request=None, action=None, trust=None, **kwargs):
    """POST /chat/action - Run a GWAY action if the session is trusted."""
    global _TRUSTS
    if request is None:
        request = gw.context.get("request")
    if not request:
        return {"error": "No request object found."}

    sid = _get_session_id(request)
    now = time.time()
    info = _TRUSTS.get(sid)

    if not info or (now - info["ts"]) > _TRUST_TTL or info["count"] > _TRUST_MAX_ACTIONS:
        secret = _random_passphrase()
        _TRUSTS[sid] = {"trust": secret, "ts": now, "count": 0}
        print(f"[web.chat] Session {sid} requires passphrase: {secret}")
        return {
            "auth_required": True,
            "message": "Please provide the passphrase displayed in the server console.",
            "secret": None,
        }

    if not trust or trust != info["trust"]:
        return {
            "auth_required": True,
            "message": "Invalid or missing passphrase. Re-authenticate.",
            "secret": None,
        }

    action_name = action or kwargs.pop("action", None)
    if not action_name:
        return {"error": "No action specified."}

    try:
        func = gw[action_name]
    except Exception as e:
        return {"error": f"Action {action_name} not found: {e}"}

    try:
        result = func(**kwargs)
    except Exception as e:
        return {"error": f"Failed to run action {action_name}: {e}"}

    info["count"] += 1
    info["ts"] = now
    return {
        "result": result,
        "remaining": max(0, _TRUST_MAX_ACTIONS - info["count"]),
    }


def api_get_manifest(*, request=None, **kwargs):
    """Return a minimal manifest for ChatGPT Actions."""
    base_url = gw.web.build_url("api", "web", "chat", "openapi.json")
    return {
        "schema_version": "v1",
        "name_for_human": "GWAY Chat Actions",
        "name_for_model": "gway_actions",
        "description_for_human": "Invoke GWAY utilities via ChatGPT Actions.",
        "description_for_model": "Run registered GWAY actions using authenticated requests.",
        "api": {
            "type": "openapi",
            "url": base_url,
        },
        "auth": {
            "type": "none"
        },
        "logo_url": gw.web.build_url("static", "favicon.ico"),
        "contact_email": "support@example.com",
        "legal_info_url": gw.web.build_url("site", "reader", tome="web/chat"),
    }


def api_get_openapi_json(*, request=None, **kwargs):
    """Return a very small OpenAPI schema for the /chat/action endpoint."""
    server_url = gw.web.base_url()
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "GWAY Chat Actions",
            "version": gw.version(),
        },
        "servers": [{"url": server_url}],
        "paths": {
            "/chat/action": {
                "post": {
                    "operationId": "chat_action",
                    "summary": "Run a GWAY action",
                    "parameters": [],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "action": {"type": "string"},
                                        "trust": {"type": "string"},
                                    },
                                    "required": ["action", "trust"],
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Result of the action"
                        }
                    }
                }
            }
        }
    }


def api_post_trust(*, request=None, trust=None, **kwargs):
    """POST /chat/trust - Authenticate with the current passphrase."""
    sid = _get_session_id(request)
    info = _TRUSTS.get(sid)
    now = time.time()
    if not info or (now - info["ts"]) > _TRUST_TTL:
        return {
            "auth_required": True,
            "message": "Passphrase expired or session missing. Request a new action.",
            "secret": None,
        }
    if trust == info["trust"]:
        info["ts"] = now
        return {"authenticated": True, "message": "Session trusted."}
    return {"authenticated": False, "message": "Invalid passphrase."}


def view_trust_status(*, request=None, **kwargs):
    sid = _get_session_id(request)
    info = _TRUSTS.get(sid)
    if not info:
        return "No passphrase issued for this session."
    remaining = int(_TRUST_TTL - (time.time() - info["ts"]))
    return f"Session trusted. Key: {info['trust']} (used {info['count']} times, expires in {remaining}s)"
