# file: projects/gpt/actions.py

import time
import uuid

from gway import gw

# In-memory trust store: {session_id: {"trust": ..., "ts": ..., "count": ...}}
# Could be replaced with Redis or similar for horizontal scaling

_TRUSTS = {}
_TRUST_TTL = 900  # 15 min default
_TRUST_MAX_ACTIONS = 20

def _get_session_id(request):
    # Use IP + UA + session cookie + random fallback
    ip = request.remote_addr or 'unknown'
    ua = request.headers.get('User-Agent', '')
    cookie = request.cookies.get('gpt_session', '')
    # You could add a hash for real-world use
    return f"{ip}:{ua}:{cookie}"


def api_post_action(*, request=None, action=None, trust=None, **kwargs):
    """
    POST /gpt/action
    Run a GWAY action if user has trusted this session with a secret key.
    Supports dot notation (e.g., project.func, project.sub.func).
    """
    global _TRUSTS
    if request is None:
        request = gw.context.get("request")
    if not request:
        return {"error": "No request object found."}

    sid = _get_session_id(request)

    trust_info = _TRUSTS.get(sid)
    now = time.time()

    if not trust_info or (now - trust_info["ts"]) > _TRUST_TTL or trust_info["count"] > _TRUST_MAX_ACTIONS:
        secret = uuid.uuid4().hex
        _TRUSTS[sid] = {"trust": secret, "ts": now, "count": 0}
        print(f"[GWAY GPT] Session {sid} needs trust. Provide this key to your chat UI: {secret}")
        return {
            "auth_required": True,
            "message": "Please authenticate by pasting the trust key displayed in your GWAY server console.",
            "secret": None,
        }

    if not trust or trust != trust_info["trust"]:
        return {
            "auth_required": True,
            "message": "Invalid or missing trust key. Please re-authenticate.",
            "secret": None,
        }

    action_name = (action or kwargs.pop("action", None))
    if not action_name:
        return {"error": "No action specified."}

    # --- Dotted lookup ---
    try:
        func = gw[action_name]   # This supports builtins and dot notation
    except Exception as e:
        return {"error": f"Action {action_name} not found: {e}"}

    try:
        result = func(**kwargs)
    except Exception as e:
        return {"error": f"Failed to run action {action_name}: {e}"}

    trust_info["count"] += 1
    trust_info["ts"] = now
    return {
        "result": result,
        "remaining": max(0, _TRUST_MAX_ACTIONS - trust_info["count"]),
    }


def api_post_trust(*, request=None, trust=None, **kwargs):
    """
    POST /gpt/trust
    Authenticate with a trust key for this session.
    """
    sid = _get_session_id(request)
    trust_info = _TRUSTS.get(sid)
    now = time.time()
    if not trust_info or (now - trust_info["ts"]) > _TRUST_TTL:
        return {
            "auth_required": True,
            "message": "Trust key expired or session missing. Please request a new action.",
            "secret": None,
        }
    if trust == trust_info["trust"]:
        trust_info["ts"] = now
        return {"authenticated": True, "message": "Session trusted."}
    else:
        return {"authenticated": False, "message": "Invalid trust key."}


# (Optionally: simple view for testing/debug)
def view_trust_status(*, request=None, **kwargs):
    sid = _get_session_id(request)
    info = _TRUSTS.get(sid)
    if not info:
        return "No trust key issued for this session."
    return f"Session is trusted. Key: {info['trust']} (used {info['count']} times, expires in {int(_TRUST_TTL - (time.time() - info['ts']))}s)"

