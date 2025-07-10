# file: projects/web/chat/actions.py
"""ChatGPT Actions utilities with simple passphrase authentication."""

import time
import random
import json
from gway import gw

_db_conn = None


def _open_db():
    global _db_conn
    if _db_conn is None:
        _db_conn = gw.sql.open_connection("work/chatlog.sqlite")
        _init_db(_db_conn)
    return _db_conn


def _init_db(conn):
    gw.sql.execute(
        """
        CREATE TABLE IF NOT EXISTS chatlog(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts INTEGER,
            direction TEXT,
            message TEXT
        )
        """,
        connection=conn,
    )


def _record(direction: str, message):
    conn = _open_db()
    gw.sql.execute(
        "INSERT INTO chatlog(ts, direction, message) VALUES (?,?,?)",
        args=(int(time.time()), direction, json.dumps(message, ensure_ascii=False)),
        connection=conn,
    )

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
        res = {"error": "No request object found."}
        _record("out", res)
        return res

    sid = _get_session_id(request)
    now = time.time()
    info = _TRUSTS.get(sid)

    # Log the incoming request payload
    _record(
        "in",
        {
            "action": action or kwargs.get("action"),
            "args": kwargs,
            "trust": trust,
            "sid": sid,
        },
    )

    if not info or (now - info["ts"]) > _TRUST_TTL or info["count"] > _TRUST_MAX_ACTIONS:
        secret = _random_passphrase()
        _TRUSTS[sid] = {"trust": secret, "ts": now, "count": 0}
        print(f"[web.chat] Session {sid} requires passphrase: {secret}")
        res = {
            "auth_required": True,
            "message": "Please provide the passphrase displayed in the server console.",
            "secret": None,
        }
        _record("out", res)
        return res

    if not trust or trust != info["trust"]:
        res = {
            "auth_required": True,
            "message": "Invalid or missing passphrase. Re-authenticate.",
            "secret": None,
        }
        _record("out", res)
        return res

    action_name = action or kwargs.pop("action", None)
    if not action_name:
        res = {"error": "No action specified."}
        _record("out", res)
        return res

    try:
        func = gw[action_name]
    except Exception as e:
        res = {"error": f"Action {action_name} not found: {e}"}
        _record("out", res)
        return res

    try:
        result = func(**kwargs)
    except Exception as e:
        res = {"error": f"Failed to run action {action_name}: {e}"}
        _record("out", res)
        return res

    info["count"] += 1
    info["ts"] = now
    res = {
        "result": result,
        "remaining": max(0, _TRUST_MAX_ACTIONS - info["count"]),
    }
    _record("out", res)
    return res


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
    _record("in", {"trust": trust, "sid": sid})
    if not info or (now - info["ts"]) > _TRUST_TTL:
        res = {
            "auth_required": True,
            "message": "Passphrase expired or session missing. Request a new action.",
            "secret": None,
        }
        _record("out", res)
        return res
    if trust == info["trust"]:
        info["ts"] = now
        res = {"authenticated": True, "message": "Session trusted."}
        _record("out", res)
        return res
    res = {"authenticated": False, "message": "Invalid passphrase."}
    _record("out", res)
    return res


def view_trust_status(*, request=None, **kwargs):
    sid = _get_session_id(request)
    info = _TRUSTS.get(sid)
    if not info:
        return "No passphrase issued for this session."
    remaining = int(_TRUST_TTL - (time.time() - info["ts"]))
    return f"Session trusted. Key: {info['trust']} (used {info['count']} times, expires in {remaining}s)"


def view_audit_chatlog(*, page: int = 1):
    """Display stored chat messages with pagination."""
    import html

    try:
        page = int(page)
    except Exception:
        page = 1
    if page < 1:
        page = 1

    offset = (page - 1) * 20
    rows = gw.sql.execute(
        "SELECT id, ts, direction, message FROM chatlog ORDER BY id DESC LIMIT 20 OFFSET ?",
        connection=_open_db(),
        args=(offset,),
    )

    parts = ["<h1>Chat API Audit Log</h1>", "<ul>"]
    for rid, ts, direction, msg in rows:
        ts_fmt = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts or 0))
        msg_html = html.escape(msg or "")
        parts.append(
            f"<li><strong>{direction}</strong> #{rid} <em>{ts_fmt}</em><pre>{msg_html}</pre></li>"
        )
    parts.append("</ul>")

    prev_link = ""
    next_link = ""
    if page > 1:
        prev_url = gw.web.app.build_url("audit-chatlog", page=page - 1)
        prev_link = f"<a href='{prev_url}'>Previous</a>"
    if rows and len(rows) >= 20:
        next_url = gw.web.app.build_url("audit-chatlog", page=page + 1)
        next_link = f"<a href='{next_url}'>Next</a>"
    if prev_link or next_link:
        parts.append("<p>")
        if prev_link:
            parts.append(prev_link)
        if prev_link and next_link:
            parts.append(" | ")
        if next_link:
            parts.append(next_link)
        parts.append("</p>")

    return "".join(parts)
